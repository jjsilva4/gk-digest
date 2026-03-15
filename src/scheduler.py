"""
One-time setup script to install/uninstall the launchd job.

Usage:
    python src/scheduler.py install
    python src/scheduler.py uninstall
"""

import os
import subprocess
import sys

LABEL = "com.gitkraken.gk-digest"
PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _python_path() -> str:
    return sys.executable


def generate_plist() -> str:
    project_root = _project_root()
    python = _python_path()
    log_path = os.path.join(project_root, "output", "launchd.log")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{os.path.join(project_root, "main.py")}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{project_root}</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>
        <key>Hour</key>
        <integer>23</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>{log_path}</string>

    <key>StandardErrorPath</key>
    <string>{log_path}</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def install():
    plist_content = generate_plist()
    os.makedirs(os.path.dirname(PLIST_PATH), exist_ok=True)

    with open(PLIST_PATH, "w") as f:
        f.write(plist_content)

    result = subprocess.run(
        ["launchctl", "load", PLIST_PATH],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"Installed and loaded: {PLIST_PATH}")
        print("GK Digest will run every Sunday at 23:00.")
    else:
        print(f"Plist written to {PLIST_PATH} but launchctl load failed:")
        print(result.stderr)
        print("You can load it manually with:")
        print(f"  launchctl load {PLIST_PATH}")


def uninstall():
    if os.path.exists(PLIST_PATH):
        subprocess.run(["launchctl", "unload", PLIST_PATH], capture_output=True)
        os.remove(PLIST_PATH)
        print(f"Uninstalled: {PLIST_PATH}")
    else:
        print(f"No plist found at {PLIST_PATH} — nothing to uninstall.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("install", "uninstall"):
        print("Usage: python src/scheduler.py install|uninstall")
        sys.exit(1)

    if sys.argv[1] == "install":
        install()
    else:
        uninstall()
