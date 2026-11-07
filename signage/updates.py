"""Updating from the admin page.

The app runs unprivileged and can't run the installer itself. It writes
``data/update-request``; a systemd path unit (set up by install.sh) notices
the file and starts ``digital-signage-update.service`` as root, which runs the
newest installer with ``--update`` and writes its output to
``/var/log/digital-signage/update.log``. The admin page shows that log while
the update runs, including the time the app itself is restarted.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from . import BASE_DIR

UPDATE_LOG = Path(os.environ.get("SIGNAGE_UPDATE_LOG", "/var/log/digital-signage/update.log"))
UPDATE_UNIT = Path(os.environ.get("SIGNAGE_UPDATE_UNIT", "/etc/systemd/system/digital-signage-update.path"))
RESULT_RE = re.compile(r"^@@RESULT (-?\d+) (\d+)$", re.M)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
STALE_AFTER_S = 30 * 60  # a log without result that hasn't changed for this long: the update died


def _git(*args: str, timeout: float = 10) -> str:
    r = subprocess.run(["git", "-C", str(BASE_DIR), *args], capture_output=True, text=True, timeout=timeout,
                       check=False)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout) else "git failed")
    return r.stdout.strip()


def current_version() -> dict[str, Any]:
    try:
        commit, subject, date = _git("log", "-1", "--format=%H%x00%s%x00%cI").split("\x00")
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError):
        return {"commit": None, "short": None, "subject": None, "date": None, "branch": None}
    return {"commit": commit, "short": commit[:7], "subject": subject, "date": date, "branch": branch}


def check_remote() -> dict[str, Any]:
    """Compare the installed commit with the newest one on the remote branch."""
    cur = current_version()
    if not cur["branch"]:
        raise RuntimeError("Not a git checkout")
    out = _git("ls-remote", "origin", f"refs/heads/{cur['branch']}", timeout=20)
    remote = out.split()[0] if out else None
    if not remote:
        raise RuntimeError(f"Branch {cur['branch']} not found on the server")
    return {"remote": remote, "remote_short": remote[:7], "available": remote != cur["commit"]}


class Updater:
    def __init__(self, data_dir: Path, log_path: Path = UPDATE_LOG, unit_path: Path = UPDATE_UNIT):
        self.request_file = data_dir / "update-request"
        self.log_path = log_path
        self.unit_path = unit_path

    def supported(self) -> bool:
        return self.unit_path.exists()

    def _log(self) -> tuple[str, float | None]:
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
            return ANSI_RE.sub("", text), self.log_path.stat().st_mtime
        except OSError:
            return "", None

    def status(self) -> dict[str, Any]:
        text, mtime = self._log()
        matches = list(RESULT_RE.finditer(text))
        m = matches[-1] if matches else None
        result = {"code": int(m.group(1)), "finished": int(m.group(2))} if m else None
        requested = self.request_file.exists()
        running = bool(text) and result is None and mtime is not None and time.time() - mtime < STALE_AFTER_S
        lines = RESULT_RE.sub("", text).rstrip().splitlines()
        return {
            "supported": self.supported(),
            "state": "starting" if requested else "running" if running else "idle",
            "result": result,
            "log": "\n".join(lines[-400:]),
            "log_updated": mtime,
        }

    def request(self) -> None:
        if not self.supported():
            raise RuntimeError("Updating from the admin page needs the update service; run the installer's "
                               "update once on the Pi to set it up.")
        if self.status()["state"] != "idle":
            raise RuntimeError("An update is already running")
        self.request_file.write_text(str(time.time()), encoding="utf-8")
