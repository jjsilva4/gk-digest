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
    today = datetime.now(tz=timezone.utc)
    # If running Sunday (weekday=6), next day is Monday
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)
    return next_monday.strftime("%Y-%m-%d")


def week_range_label() -> str:
    today = datetime.now(tz=timezone.utc)
    week_start = today - timedelta(days=today.weekday() + 1)  # last Monday
    week_end = today
    return f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}"


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
        f"Run complete — {len(completed)} succeeded, {len(failed)} failed"
        + (f" ({', '.join(failed)})" if failed else "")
    )

    summary = (
        f"{len(completed)} subreddits done"
        + (f", {len(failed)} failed: {', '.join(failed)}" if failed else "")
        + f" — {run_dir}"
    )
    notify("GK Digest", summary)


if __name__ == "__main__":
    main()
