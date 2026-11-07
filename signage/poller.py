"""Background polling: each data source refreshes itself on its own thread.

HTTP handlers only ever read the latest snapshot, so a slow or broken
upstream API can never block or break the display. When a fetch fails the
previous data is kept and marked stale, instead of the panel disappearing.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .util import redact_secrets

logger = logging.getLogger(__name__)


class SourceDisabled(Exception):
    """Raised by a fetch function when the source is turned off/unconfigured."""


@dataclass
class Snapshot:
    data: Any = None
    status: str = "pending"  # pending | ok | error | disabled
    error: str | None = None
    updated_at: float | None = None  # last successful fetch (epoch seconds)
    attempted_at: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, max_age: float) -> dict[str, Any]:
        stale = (
            self.updated_at is not None
            and (self.status == "error" or time.time() - self.updated_at > max_age)
        )
        return {
            "status": self.status,
            "stale": stale,
            "error": self.error,
            "updated_at": _iso(self.updated_at),
            "data": self.data,
            **({"meta": self.meta} if self.meta else {}),
        }


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


class Poller:
    """Runs ``fetch()`` every ``interval()`` seconds on a daemon thread.

    ``fetch`` returns the new data (or ``(data, meta)``), raises
    ``SourceDisabled`` when switched off, or raises any other exception on
    failure. Failures back off exponentially up to ``max_backoff``.
    """

    def __init__(self, name: str, fetch: Callable[[], Any], interval: Callable[[], float],
                 max_backoff: float = 600):
        self.name = name
        self._fetch = fetch
        self._interval = interval
        self._max_backoff = max_backoff
        self._snapshot = Snapshot()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failures = 0

    @property
    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._snapshot

    def to_dict(self) -> dict[str, Any]:
        snap = self.snapshot
        # Consider data stale once it is older than ~3 refresh intervals.
        return snap.to_dict(max_age=max(self._interval() * 3, 60))

    def refresh_now(self) -> None:
        self._wake.set()

    def run_once(self) -> None:
        now = time.time()
        try:
            result = self._fetch()
            meta: dict[str, Any] = {}
            if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
                result, meta = result
            with self._lock:
                self._snapshot = Snapshot(data=result, status="ok", updated_at=now, attempted_at=now, meta=meta)
            self._failures = 0
        except SourceDisabled as e:
            with self._lock:
                self._snapshot = Snapshot(status="disabled", error=str(e) or None, attempted_at=now)
            self._failures = 0
        except Exception as e:  # keep last good data, mark as error
            self._failures += 1
            logger.warning("%s: fetch failed (%d in a row): %s", self.name, self._failures, redact_secrets(str(e)))
            with self._lock:
                prev = self._snapshot
                self._snapshot = Snapshot(
                    data=prev.data if prev.status in ("ok", "error") else None,
                    status="error",
                    error=_short_error(e),
                    updated_at=prev.updated_at,
                    attempted_at=now,
                    meta=prev.meta,
                )

    def _next_delay(self) -> float:
        base = max(float(self._interval()), 1.0)
        if self._failures:
            return min(base * (2 ** min(self._failures - 1, 6)), max(self._max_backoff, base))
        return base

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._wake.wait(self._next_delay())
            self._wake.clear()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name=f"poller-{self.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()


def _short_error(e: Exception) -> str:
    # Errors can end up on the public display endpoint; never let an API key through.
    msg = redact_secrets(str(e)) or e.__class__.__name__
    return msg if len(msg) <= 200 else msg[:197] + "..."
