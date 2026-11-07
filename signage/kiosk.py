"""Remote control of the screen and health monitoring.

Three parties:

* the **display page** on the Pi's own browser: every poll from it counts as
  a sign of life ("the TV shows the dashboard");
* the **kiosk agent** (``kiosk/agent.py``), a small program in the Pi's
  desktop session that starts Chromium, restarts it when it crashes or the
  page stops polling, and carries out commands (restart browser, reboot,
  screenshot);
* the **admin page**, which queues those commands and shows the status.

Agent and display are recognised the same way as the screen-sharing
receiver: requests from this machine that did not come through a proxy or
Cloudflare (``share.is_local_screen``).

The optional heartbeat pings an external monitor (e.g. healthchecks.io)
every few minutes; if the pings stop or report a failure, that service
alerts you (Telegram, push, e-mail, ...). Without a URL nothing is sent.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

from .share import Mailbox

logger = logging.getLogger(__name__)

AGENT_POLL_TIMEOUT_S = 25
AGENT_TIMEOUT_S = 60  # agent counts as offline after this
DISPLAY_TIMEOUT_S = 90  # display counts as frozen after this (it polls every 5 s)
MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
STARTUP_GRACE_S = 180  # after a server start, wait this long for the display before reporting a failure
COMMANDS = ("restart-browser", "reboot", "screenshot")


class KioskHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.commands = Mailbox()
        self.poll_timeout: float = AGENT_POLL_TIMEOUT_S
        self.display_seen = 0.0
        self.agent_seen = 0.0
        self.agent_info: dict[str, Any] = {}
        self.reload_token = 0
        self.screenshot: bytes | None = None
        self.screenshot_type = "image/jpeg"
        self.screenshot_at = 0.0
        self.screenshot_requested = 0.0
        self.screenshot_error = ""
        self.screenshot_error_at = 0.0
        self.started = time.time()

    # --- display ---------------------------------------------------------------
    def display_alive(self, now: float | None = None) -> bool:
        return (now or time.time()) - self.display_seen < DISPLAY_TIMEOUT_S

    def request_reload(self) -> None:
        """The display reloads when this token changes (it's part of the build id)."""
        with self._lock:
            self.reload_token += 1

    # --- agent -----------------------------------------------------------------
    def agent_online(self, now: float | None = None) -> bool:
        return (now or time.time()) - self.agent_seen < AGENT_TIMEOUT_S

    def queue(self, command: str) -> None:
        if command not in COMMANDS:
            raise ValueError(f"unknown command {command}")
        if command == "screenshot":
            self.screenshot_requested = time.time()
        self.commands.put({"command": command, "at": time.time()})
        logger.info("Kiosk command queued: %s", command)

    def agent_poll(self, since: int, info: dict[str, Any]) -> dict[str, Any]:
        self.agent_seen = time.time()
        if info:
            self.agent_info = {k: str(v)[:100] for k, v in list(info.items())[:10]}
        if since > self.commands.seq:
            since = self.commands.seq  # server restarted: don't replay old commands
        events, seq = self.commands.get(since, self.poll_timeout)
        self.agent_seen = time.time()
        # Commands older than a minute are stale (e.g. agent was offline).
        fresh = [e for e in events if time.time() - e["at"] < 60]
        return {"commands": [e["command"] for e in fresh], "seq": seq,
                "display_age": round(time.time() - self.display_seen) if self.display_seen else None}

    def store_screenshot(self, data: bytes, content_type: str) -> None:
        with self._lock:
            self.screenshot = data
            self.screenshot_type = content_type if content_type in ("image/png", "image/jpeg") else "image/jpeg"
            self.screenshot_at = time.time()

    def store_screenshot_error(self, message: str) -> None:
        with self._lock:
            self.screenshot_error = message[:300]
            self.screenshot_error_at = time.time()

    def status(self) -> dict[str, Any]:
        now = time.time()
        answered = max(self.screenshot_at, self.screenshot_error_at)
        failed = self.screenshot_error_at > self.screenshot_at and self.screenshot_error_at >= self.screenshot_requested
        return {
            "display_online": self.display_alive(now),
            "display_seen": self.display_seen or None,
            "agent_online": self.agent_online(now),
            "agent_seen": self.agent_seen or None,
            "agent": self.agent_info,
            "screenshot_at": self.screenshot_at or None,
            "screenshot_pending": self.screenshot_requested > answered,
            # Asked more than 20 s ago and no answer: the helper is probably stuck or outdated.
            "screenshot_timeout": self.screenshot_requested > answered and now - self.screenshot_requested > 20,
            "screenshot_error": self.screenshot_error if failed else None,
            "server_started": self.started,
        }


def send_heartbeat(session: requests.Session, cfg: dict[str, Any], hub: KioskHub) -> dict[str, Any]:
    """Ping the monitoring URL; append /fail when the screen isn't showing the dashboard.

    The /fail suffix is the healthchecks.io convention; other services that
    just expect regular requests can ignore it (turn off "require_display").
    """
    url = (cfg.get("heartbeat_url") or "").strip()
    # Right after a (re)boot the browser needs a moment to load the dashboard;
    # don't report that as a failure.
    starting = not hub.display_seen and time.time() - hub.started < STARTUP_GRACE_S
    healthy = hub.display_alive() or starting or not cfg.get("require_display", True)
    target = url if healthy else url.rstrip("/") + "/fail"
    resp = session.get(target, timeout=(5, 10))
    if resp.status_code >= 400:
        raise RuntimeError(f"heartbeat HTTP {resp.status_code}")
    return {"healthy": healthy}
