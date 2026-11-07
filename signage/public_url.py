"""The dashboard's public address (e.g. a Cloudflare tunnel hostname).

Not configured anywhere by default: the first request that arrives through
Cloudflare tells us the hostname people use, and it is remembered in
``data/public_url.json``. An address set in the admin page wins.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Any, Callable

from .storage import read_json, write_json

logger = logging.getLogger(__name__)

HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}(:\d{1,5})?$")


class PublicUrl:
    def __init__(self, path: Path, override: Callable[[], str]):
        self.path = path
        self._override = override
        self._lock = threading.Lock()
        self._detected: str = (read_json(path, {}) or {}).get("url", "")

    def get(self) -> str:
        return self._override() or self._detected

    @property
    def detected(self) -> str:
        return self._detected

    def observe(self, headers: Any, host: str) -> None:
        """Remember the host of a request that came through Cloudflare."""
        if not headers.get("Cf-Connecting-Ip") or not HOST_RE.match(host or ""):
            return
        url = f"https://{host.lower()}"  # Cloudflare always serves HTTPS to visitors
        if url == self._detected:
            return
        with self._lock:
            self._detected = url
            try:
                write_json(self.path, {"url": url})
            except OSError as e:
                logger.warning("Could not save public address: %s", e)
        logger.info("Public address detected: %s", url)
