import os
import logging
import yaml
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from src.collector import get_reddit_client, fetch_subreddit_posts
from src.pdf_builder import build_pdf
from src.notifier import notify

load_dotenv()


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def output_folder_date() -> str:
    """Returns the date string for the output folder (next Monday from today's perspective)."""
    today = pipeline_now()
    # If running Sunday (weekday=6), next day is Monday
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)
    return next_monday.strftime("%Y-%m-%d")


def week_range_label() -> str:
    today = pipeline_now()
    week_start = today - timedelta(days=today.weekday() + 1)  # last Monday
    week_end = today
    return f"{week_start.strftime('%b %d')}-{week_end.strftime('%b %d, %Y')}"


def pipeline_now() -> datetime:
    """
    Allow forcing a run date via GK_DIGEST_NOW_UTC for backfills or reproducible reruns.
    Accepted examples: 2026-03-22 or 2026-03-22T19:00:00+00:00
    """
    raw = os.getenv("GK_DIGEST_NOW_UTC")
    if not raw:
        return datetime.now(tz=timezone.utc)

    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def setup_logging(log_path: str) -> logging.Logger:
    logger = logging.getLogger("gk-digest")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(log_path)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


def main():
    config = load_config()
    settings = config["settings"]
    subreddits = [s for s in config["subreddits"] if s.get("enabled", True)]
    gemini_cfg = config.get("gemini", {})
    git_cfg = config.get("git", {})

    folder_name = output_folder_date()
    output_base = settings.get("output_dir", "output")
    run_dir = os.path.join(output_base, folder_name)
    os.makedirs(run_dir, exist_ok=True)

    log_path = os.path.join(run_dir, "run.log")
    logger = setup_logging(log_path)

    week_range = week_range_label()
    logger.info(f"GK Digest run started — {len(subreddits)} subreddits — {week_range}")

    reddit = get_reddit_client()

    completed = []
    failed = []

    for entry in subreddits:
        name = entry["name"]
        try:
            logger.info(f"Fetching r/{name} ...")
            posts = fetch_subreddit_posts(reddit, name, settings)
            logger.info(f"  r/{name}: {len(posts)} qualifying posts")

            if not posts:
                logger.info(f"  r/{name}: no qualifying posts — skipping PDF")
                completed.append(name)
                continue

            pdf_path = os.path.join(run_dir, f"{name}.pdf")
            build_pdf(name, posts, pdf_path, week_range)
            logger.info(f"  r/{name}: PDF written to {pdf_path}")
            completed.append(name)

        except Exception as e:
            logger.error(f"  r/{name}: FAILED — {e}")
            failed.append(name)

    logger.info(
        f"PDF phase complete — {len(completed)} succeeded, {len(failed)} failed"
        + (f" ({', '.join(failed)})" if failed else "")
    )

    # ── Gemini analysis pipeline ──────────────────────────────────────────────
    analysis_path = None
    if gemini_cfg.get("enabled", False):
        if not completed:
            logger.warning("Gemini: skipping — no PDFs were generated")
        else:
            try:
                from src.gemini_analyzer import run_pipeline
                analysis_path = run_pipeline(
                    run_dir=run_dir,
                    week_range=week_range,
                    batch_size=gemini_cfg.get("batch_size", 10),
                    model_name=gemini_cfg.get("model", "gemini-1.5-pro"),
                    logger=logger,
                )
            except Exception as e:
                logger.error(f"Gemini pipeline FAILED — {e}")
    else:
        logger.info("Gemini: disabled in config — skipping analysis")

    # ── Dashboard rebuild ─────────────────────────────────────────────────────
    if analysis_path:
        try:
            from src.dashboard_builder import build, discover_archive_entries
            docs_path = os.path.join(os.path.dirname(__file__), "docs", "index.html")
            docs_dir = os.path.dirname(docs_path)
            archive_entries = discover_archive_entries(output_base, docs_dir)
            latest_run_key = os.path.basename(run_dir)
            archive_options = [
                {
                    "label": entry["label"],
                    "url": entry["archive_url"] if entry["run_key"] != latest_run_key else "index.html",
                    "current": entry["run_key"] == latest_run_key,
                }
                for entry in reversed(archive_entries)
            ]

            for entry in archive_entries:
                page_archive_options = [
                    {
                        "label": option["label"],
                        "url": "index.html" if candidate["run_key"] == latest_run_key else candidate["archive_url"],
                        "current": candidate["run_key"] == entry["run_key"],
                    }
                    for option, candidate in zip(reversed(archive_options), reversed(archive_entries))
                ]
                build(
                    analysis_path=entry["analysis_path"],
                    output_path=entry["archive_output_path"],
                    archive_options=page_archive_options,
                )

            build(
                analysis_path=analysis_path,
                output_path=docs_path,
                archive_options=archive_options,
            )
            logger.info(f"Dashboard rebuilt → {docs_path}")
        except Exception as e:
            logger.error(f"Dashboard build FAILED — {e}")
            analysis_path = None  # prevent git push if dashboard failed

    # ── Git push ──────────────────────────────────────────────────────────────
    if analysis_path and git_cfg.get("auto_push", False):
        try:
            from src.git_publisher import publish
            repo_dir = os.path.dirname(os.path.abspath(__file__))
            publish(week_range=week_range, repo_dir=repo_dir, logger=logger)
        except Exception as e:
            logger.error(f"Git push FAILED — {e}")

    # ── macOS notification ────────────────────────────────────────────────────
    summary = (
        f"{len(completed)} subreddits done"
        + (f", {len(failed)} failed: {', '.join(failed)}" if failed else "")
        + (", dashboard updated" if analysis_path else "")
        + f" — {run_dir}"
    )
    notify("GK Digest", summary)


if __name__ == "__main__":
    main()
