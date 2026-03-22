import logging
import subprocess


def publish(week_range: str, repo_dir: str, logger: logging.Logger) -> None:
    """
    Stage dashboard pages, commit with a weekly label, and push to origin.
    """
    def run(cmd: list[str]):
        result = subprocess.run(
            cmd, cwd=repo_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Git command failed: {' '.join(cmd)}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )
        return result.stdout.strip()

    logger.info("Git: staging dashboard pages...")
    run(["git", "add", "docs/index.html", "docs/digests"])

    commit_msg = f"Weekly digest \u2014 {week_range}"
    logger.info(f"Git: committing '{commit_msg}'...")
    run(["git", "commit", "-m", commit_msg])

    logger.info("Git: pushing to origin...")
    run(["git", "push"])

    logger.info("Git: dashboard pushed — GitHub Pages will update shortly.")
