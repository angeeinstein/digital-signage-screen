#!/usr/bin/env python3
"""Kiosk helper for the digital signage screen.

Runs in the Pi's desktop session (started by the desktop's autostart, set up
by install.sh). It

* starts Chromium in kiosk mode on the dashboard and restarts it when it
  exits or crashes;
* restarts it when the dashboard page stops polling the server (frozen tab);
* carries out commands from the admin page: restart the browser, reboot the
  Pi, take a screenshot.

Standard library only, so it runs with the system Python. Only one instance
runs per user (lock file).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import logging.handlers
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "3"
FROZEN_AFTER_S = 120  # restart the browser when the page hasn't polled for this long
STARTUP_GRACE_S = 180  # ... but give a fresh browser this long to load first
BROWSERS = ("chromium", "chromium-browser", "google-chrome")

log = logging.getLogger("kiosk")


def browser_command(url: str, profile: Path) -> list[str]:
    binary = next((b for b in BROWSERS if shutil.which(b)), None)
    if not binary:
        raise SystemExit(f"No Chromium found (tried: {', '.join(BROWSERS)})")
    return [
        binary,
        "--kiosk",
        f"--user-data-dir={profile}",
        "--noerrdialogs",
        "--disable-infobars",
        "--disable-session-crashed-bubble",
        "--disable-features=Translate",
        "--no-first-run",
        "--check-for-update-interval=31536000",
        "--autoplay-policy=no-user-gesture-required",
        "--password-store=basic",
        url,
    ]


def mark_clean_exit(profile: Path) -> None:
    """Stop Chromium from offering to "restore pages" after a crash or reboot."""
    prefs = profile / "Default" / "Preferences"
    try:
        data = json.loads(prefs.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    profile_prefs = data.setdefault("profile", {})
    profile_prefs["exited_cleanly"] = True
    profile_prefs["exit_type"] = "Normal"
    try:
        prefs.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


class Browser:
    """Keeps one Chromium process running."""

    def __init__(self, url: str, profile: Path):
        self.url = url
        self.profile = profile
        self.proc: subprocess.Popen | None = None
        self.started = 0.0
        self.crashes = 0
        self.expected_exit = False
        self.paused = False  # set while the helper replaces itself
        self._lock = threading.Lock()

    def ensure_running(self) -> None:
        with self._lock:
            if self.paused or (self.proc and self.proc.poll() is None):
                return
            if self.proc is not None and not self.expected_exit:
                code = self.proc.returncode
                quick = time.time() - self.started < 30
                self.crashes = self.crashes + 1 if quick else 0
                log.warning("Browser exited (code %s); restarting", code)
                if self.crashes:
                    time.sleep(min(60, 3 * 2 ** min(self.crashes, 4)))  # back off if it keeps crashing
            self.expected_exit = False
            mark_clean_exit(self.profile)
            cmd = browser_command(self.url, self.profile)
            log.info("Starting %s", cmd[0])
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         start_new_session=True)
            self.started = time.time()

    def restart(self, reason: str) -> None:
        with self._lock:
            proc = self.proc
        if not proc or proc.poll() is not None:
            return
        log.warning("Restarting browser: %s", reason)
        self.expected_exit = True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def uptime(self) -> float:
        return time.time() - self.started if self.started else 0.0


class ScreenshotError(Exception):
    pass


def display_env() -> dict[str, str]:
    """Environment for screenshot tools, with the Wayland display filled in.

    Programs started by the desktop's autostart don't always get
    WAYLAND_DISPLAY; the socket is in XDG_RUNTIME_DIR, so look for it there.
    """
    env = dict(os.environ)
    runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    env["XDG_RUNTIME_DIR"] = runtime
    if not env.get("WAYLAND_DISPLAY"):
        sockets = sorted(p.name for p in Path(runtime).glob("wayland-*") if not p.name.endswith(".lock"))
        if sockets:
            env["WAYLAND_DISPLAY"] = sockets[0]
    return env


def take_screenshot() -> tuple[bytes, str]:
    env = display_env()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "screen.png"
        if env.get("WAYLAND_DISPLAY") and shutil.which("grim"):
            # PNG: grim on Raspberry Pi OS is built without JPEG support.
            cmd = ["grim", "-t", "png", "-l", "3", "-s", "0.5", str(out)]
        elif env.get("DISPLAY") and shutil.which("scrot"):
            cmd = ["scrot", "-q", "75", str(out)]
        elif env.get("WAYLAND_DISPLAY"):
            raise ScreenshotError("grim is not installed (sudo apt install grim)")
        else:
            raise ScreenshotError("No display found for the screenshot")
        try:
            r = subprocess.run(cmd, timeout=20, capture_output=True, env=env, check=False)
        except (subprocess.SubprocessError, OSError) as e:
            raise ScreenshotError(f"{cmd[0]} could not run: {e}") from None
        if r.returncode != 0 or not out.exists():
            detail = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            raise ScreenshotError(f"{cmd[0]} failed: {detail[-1] if detail else f'exit code {r.returncode}'}")
        data = out.read_bytes()
        return data, "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"


def reboot() -> None:
    log.warning("Rebooting on request from the admin page")
    # Allowed without password by /etc/sudoers.d/digital-signage-kiosk (set up by install.sh).
    subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "reboot"], check=False)


class Agent:
    def __init__(self, server: str, browser: Browser):
        self.server = server.rstrip("/")
        self.browser = browser
        self.since = 0

    def request(self, path: str, data: bytes | None = None, content_type: str = "", timeout: float = 35):
        req = urllib.request.Request(self.server + path, data=data, method="POST" if data is not None else "GET")
        req.add_header("X-Requested-With", "signage")
        if content_type:
            req.add_header("Content-Type", content_type)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def poll_once(self) -> None:
        info = {"info_version": VERSION, "info_browser_uptime": int(self.browser.uptime())}
        query = "&".join(f"{k}={v}" for k, v in info.items())
        r = self.request(f"/api/kiosk/agent/commands?since={self.since}&{query}")
        self.since = r.get("seq", self.since)
        for command in r.get("commands", []):
            self.run(command)
        age = r.get("display_age")
        if age is not None and age > FROZEN_AFTER_S and self.browser.uptime() > STARTUP_GRACE_S:
            self.browser.restart(f"dashboard hasn't updated for {age} s")

    def run(self, command: str) -> None:
        log.info("Command: %s", command)
        if command == "restart-browser":
            self.browser.restart("requested from the admin page")
        elif command == "reboot":
            reboot()
        elif command == "screenshot":
            try:
                data, content_type = take_screenshot()
            except ScreenshotError as e:
                log.error("Screenshot failed: %s", e)
                body = json.dumps({"error": str(e)[:300]}).encode("utf-8")
                self.request("/api/kiosk/agent/screenshot-error", data=body, content_type="application/json")
                return
            self.request("/api/kiosk/agent/screenshot", data=data, content_type=content_type, timeout=30)

    def loop(self) -> None:
        own_file = Path(__file__).resolve()
        version = own_file.stat().st_mtime
        while True:
            if own_file.exists() and own_file.stat().st_mtime != version:
                # Updated by the installer: restart with the new code. The new
                # instance starts its own browser, so close this one first.
                log.info("Helper was updated; restarting it")
                self.browser.paused = True  # don't let the supervisor start a browser in between
                self.browser.restart("helper updated")
                os.execv(sys.executable, [sys.executable, str(own_file), *sys.argv[1:]])
            try:
                self.poll_once()
            except (urllib.error.URLError, OSError, ValueError) as e:
                # Server down or restarting: the page shows "Waiting for server" by itself.
                log.debug("Server not reachable: %s", e)
                time.sleep(5)


def single_instance(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "w")  # noqa: SIM115 - kept open for the process lifetime
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit("Kiosk helper is already running") from None
    return f


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", default="http://localhost:8080", help="dashboard address on this machine")
    p.add_argument("--profile", default=str(Path.home() / ".config" / "digital-signage-kiosk"))
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    # Log to ~/.cache/digital-signage-kiosk.log (autostart has no terminal), and stderr.
    log_file = Path.home() / ".cache" / "digital-signage-kiosk.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(log_file, maxBytes=512 * 1024, backupCount=1),
        logging.StreamHandler(),
    ]
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(message)s")
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    _lock = single_instance(runtime / "digital-signage-kiosk.lock")  # noqa: F841
    browser = Browser(args.url, Path(args.profile))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    threading.Thread(target=supervise, args=(browser,), daemon=True).start()
    Agent(args.url, browser).loop()


def supervise(browser: Browser) -> None:
    """Restart the browser within seconds when it exits."""
    while True:
        try:
            browser.ensure_running()
        except Exception:  # never let the supervisor die
            log.exception("Could not start the browser")
        time.sleep(2)


if __name__ == "__main__":
    main()
