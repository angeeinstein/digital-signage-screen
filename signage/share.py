"""Screen sharing from a laptop to the TV.

Flow:

1. A laptop opens ``/share`` (normally through the public Cloudflare
   address) and asks to share. The TV shows a 4-digit code for 60 s.
2. The laptop sends the code. If it matches, the laptop becomes the active
   sender (replacing anyone who was sharing before).
3. Laptop and TV exchange WebRTC setup messages through this hub
   (long-polling over normal HTTP, so it works through the tunnel). The
   video then flows directly over the local network.
4. If no direct connection comes up, the laptop records its screen with
   MediaRecorder and uploads short chunks here; the TV plays them with
   Media Source Extensions. Slower (1-2 s) but works from anywhere.

Only the display running on the Pi itself ("the screen") may receive: the
shared video must never go to someone who merely opened the public
dashboard. See ``is_local_screen``.

Everything is in memory; it relies on the single gunicorn worker.
"""

from __future__ import annotations

import hmac
import ipaddress
import logging
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

CODE_TTL_S = 30  # how long the code stays on the TV
MAX_CODE_ATTEMPTS = 5
SENDER_TIMEOUT_S = 35  # sender polls every <= 20 s
SCREEN_TIMEOUT_S = 45
POLL_TIMEOUT_S = 20
RELAY_KEEP_CHUNKS = 240  # ~60 s at 250 ms per chunk
REQUESTS_PER_MINUTE = 4  # per client address
EXTENSION_FACTOR = 0.5  # one extension adds half of the time limit
WARNING_S = 5 * 60  # the laptop offers the extension this long before the end


class ShareError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _loopback(addr: str | None) -> bool:
    try:
        return ipaddress.ip_address((addr or "").strip()).is_loopback
    except ValueError:
        return False


def is_local_screen(environ: dict[str, Any], headers: Any) -> bool:
    """True if the request comes from a browser on this machine.

    The raw socket address must be loopback (nginx or the browser itself),
    every X-Forwarded-For hop must be loopback (nginx appends the real
    client), and there must be no Cloudflare headers (the tunnel runs on
    this machine too, so its requests are otherwise "local").
    """
    raw = (environ.get("werkzeug.proxy_fix.orig") or {}).get("REMOTE_ADDR") or environ.get("REMOTE_ADDR")
    if not _loopback(raw):
        return False
    if headers.get("Cf-Connecting-Ip") or headers.get("Cf-Ray"):
        return False
    xff = headers.get("X-Forwarded-For", "")
    return all(_loopback(hop) for hop in xff.split(",") if hop.strip())


class Mailbox:
    """Numbered message queue with long-polling."""

    def __init__(self) -> None:
        self._msgs: deque[tuple[int, dict[str, Any]]] = deque(maxlen=300)
        self._seq = 0
        self._cond = threading.Condition()

    def put(self, msg: dict[str, Any]) -> None:
        with self._cond:
            self._seq += 1
            self._msgs.append((self._seq, msg))
            self._cond.notify_all()

    def wake(self) -> None:
        with self._cond:
            self._cond.notify_all()

    @property
    def seq(self) -> int:
        return self._seq

    def get(self, since: int, timeout: float) -> tuple[list[dict[str, Any]], int]:
        with self._cond:
            if since > self._seq:  # server restarted; start over
                since = 0
            self._cond.wait_for(lambda: self._seq > since, timeout)
            return [m for s, m in self._msgs if s > since], self._seq


class RelayBuffer:
    """Recent video chunks of the fallback stream."""

    def __init__(self) -> None:
        self.session = ""
        self.mime = ""
        self._chunks: dict[int, bytes] = {}
        self._last = -1
        self._cond = threading.Condition()

    def reset(self, session: str, mime: str) -> None:
        with self._cond:
            self.session, self.mime = session, mime
            self._chunks.clear()
            self._last = -1
            self._cond.notify_all()

    def put(self, session: str, seq: int, data: bytes) -> None:
        with self._cond:
            if session != self.session:
                raise ShareError("Unknown stream", 409)
            if seq != self._last + 1:
                raise ShareError(f"Expected chunk {self._last + 1}", 409)
            self._chunks[seq] = data
            self._last = seq
            for old in [s for s in self._chunks if s <= seq - RELAY_KEEP_CHUNKS]:
                del self._chunks[old]
            self._cond.notify_all()

    def get(self, session: str, after: int, timeout: float) -> tuple[str, int, bytes]:
        """Returns ("chunk", seq, data), ("wait", after, b""), ("gap", ..) or ("gone", ..)."""
        with self._cond:
            self._cond.wait_for(lambda: session != self.session or self._last > after, timeout)
            if session != self.session:
                return "gone", after, b""
            if self._last <= after:
                return "wait", after, b""
            if after + 1 not in self._chunks:
                return "gap", after, b""
            # Send everything that is ready, so a slow screen catches up.
            seqs = range(after + 1, self._last + 1)
            return "chunk", self._last, b"".join(self._chunks[s] for s in seqs)


@dataclass
class Sender:
    id: str
    token: str
    name: str
    client: str
    code: str
    created: float
    last_seen: float
    attempts: int = 0
    verified: bool = False
    limit_s: float = 0  # time limit when sharing started; 0 = none
    ends_at: float | None = None
    extended: bool = False
    mailbox: Mailbox = field(default_factory=Mailbox)

    def deadline_message(self, now: float) -> dict[str, Any]:
        return {
            "type": "deadline",
            "remaining": None if self.ends_at is None else max(0.0, self.ends_at - now),
            "can_extend": self.ends_at is not None and not self.extended,
            "extend_minutes": round(self.limit_s * EXTENSION_FACTOR / 60),
            "warning_s": WARNING_S,
        }


class ShareHub:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._senders: dict[str, Sender] = {}  # by token
        self._pending: str | None = None  # token waiting for its code
        self._active: str | None = None  # token currently shown
        self._mode = ""  # "direct" | "relay"
        self._requests: dict[str, deque[float]] = {}
        self.screen = Mailbox()
        self.screen_seen = 0.0
        self.relay = RelayBuffer()
        self.poll_timeout: float = POLL_TIMEOUT_S

    # --- helpers ---------------------------------------------------------------
    def _cleanup(self, now: float) -> None:
        for token, s in list(self._senders.items()):
            stale = now - s.last_seen > SENDER_TIMEOUT_S
            expired = not s.verified and now - s.created > CODE_TTL_S
            if stale or (expired and token != self._active):
                self._drop(token, "timeout")
            elif s.ends_at is not None and now >= s.ends_at:
                self._drop(token, "time limit")

    def _drop(self, token: str, reason: str) -> None:
        s = self._senders.pop(token, None)
        if not s:
            return
        s.mailbox.put({"type": "ended", "reason": reason})
        if token == self._pending:
            self._pending = None
            self._publish_state()
        if token == self._active:
            self._active = None
            self._mode = ""
            self.relay.reset("", "")
            self.screen.put({"type": "stop", "sender": s.id})
            self._publish_state()
            logger.info("Screen sharing by %s ended (%s)", s.name, reason)

    def state(self) -> dict[str, Any]:
        with self._lock:
            pending = self._senders.get(self._pending or "")
            active = self._senders.get(self._active or "")
            return {
                "pending": {"code": pending.code, "name": pending.name,
                            "expires": pending.created + CODE_TTL_S, "ttl": CODE_TTL_S} if pending else None,
                "active": {"id": active.id, "name": active.name, "mode": self._mode,
                           "ends_at": active.ends_at, "extended": active.extended} if active else None,
            }

    def _publish_state(self) -> None:
        self.screen.put({"type": "state", "state": self.state()})

    def _sender(self, token: str, now: float, verified: bool = True) -> Sender:
        s = self._senders.get(token or "")
        if not s:
            raise ShareError("This share session has ended. Start again.", 410)
        if verified and not s.verified:
            raise ShareError("Enter the code first", 403)
        s.last_seen = now
        return s

    def screen_online(self, now: float | None = None) -> bool:
        return (now or time.time()) - self.screen_seen < SCREEN_TIMEOUT_S

    # --- sender side -------------------------------------------------------------
    def request(self, name: str, client: str, now: float | None = None) -> dict[str, Any]:
        now = now or time.time()
        with self._lock:
            self._cleanup(now)
            hits = self._requests.setdefault(client, deque())
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= REQUESTS_PER_MINUTE:
                raise ShareError("Too many attempts. Wait a minute and try again.", 429)
            if not self.screen_online(now):
                raise ShareError("The TV is not connected right now.", 503)
            hits.append(now)
            if self._pending:
                self._drop(self._pending, "replaced")
            token = secrets.token_urlsafe(24)
            s = Sender(id=secrets.token_hex(6), token=token, name=(name or "").strip()[:40] or "A laptop",
                       client=client, code=f"{secrets.randbelow(10000):04d}", created=now, last_seen=now)
            self._senders[token] = s
            self._pending = token
            self._publish_state()
            return {"token": token, "expires_in": CODE_TTL_S}

    def verify(self, token: str, code: str, now: float | None = None, limit_s: float = 0) -> dict[str, Any]:
        now = now or time.time()
        with self._lock:
            self._cleanup(now)
            s = self._sender(token, now, verified=False)
            if s.verified:
                return {"id": s.id}
            s.attempts += 1
            if not hmac.compare_digest(s.code, (code or "").strip()):
                left = MAX_CODE_ATTEMPTS - s.attempts
                if left <= 0:
                    self._drop(token, "too many wrong codes")
                    raise ShareError("Wrong code too many times. Start again.", 403)
                raise ShareError(f"Wrong code ({left} {'try' if left == 1 else 'tries'} left)", 403)
            s.verified = True
            s.limit_s = max(0.0, limit_s)
            s.ends_at = now + s.limit_s if s.limit_s else None
            s.mailbox.put(s.deadline_message(now))
            if self._pending == token:
                self._pending = None
            if self._active and self._active != token:
                old = self._senders.get(self._active)
                if old:
                    old.mailbox.put({"type": "replaced", "by": s.name})
                self._drop(self._active, "replaced")
            self._active = token
            self._mode = ""
            self._publish_state()
            logger.info("Screen sharing started by %s", s.name)
            return {"id": s.id}

    def extend(self, token: str, now: float | None = None) -> dict[str, Any]:
        """Extend the time limit once, by half of the original limit."""
        now = now or time.time()
        with self._lock:
            s = self._sender(token, now)
            if token != self._active:
                raise ShareError("Someone else is sharing now", 409)
            if s.ends_at is None:
                raise ShareError("There is no time limit", 409)
            if s.extended:
                raise ShareError("Sharing can only be extended once", 409)
            s.ends_at += s.limit_s * EXTENSION_FACTOR
            s.extended = True
            msg = s.deadline_message(now)
            s.mailbox.put(msg)
            self._publish_state()
            logger.info("Screen sharing by %s extended", s.name)
            return msg

    def sender_signal(self, token: str, msg: dict[str, Any], now: float | None = None) -> None:
        now = now or time.time()
        with self._lock:
            s = self._sender(token, now)
            if token != self._active:
                raise ShareError("Someone else is sharing now", 409)
            kind = msg.get("type")
            if kind not in ("offer", "ice", "relay", "mode"):
                raise ShareError("Unknown message")
            if kind == "relay":
                self.relay.reset(str(msg.get("session", "")), str(msg.get("mime", "")))
            if kind in ("relay", "mode"):
                self._mode = "relay" if kind == "relay" else str(msg.get("mode", ""))[:10]
                self._publish_state()
            self.screen.put({**msg, "sender": s.id})

    def sender_events(self, token: str, since: int) -> tuple[list[dict[str, Any]], int]:
        with self._lock:
            s = self._sender(token, time.time(), verified=False)
        events, seq = s.mailbox.get(since, self.poll_timeout)
        with self._lock:
            s.last_seen = time.time()
        return events, seq

    def relay_put(self, token: str, session: str, seq: int, data: bytes) -> None:
        with self._lock:
            self._sender(token, time.time())
            if token != self._active:
                raise ShareError("Someone else is sharing now", 409)
        self.relay.put(session, seq, data)

    def stop(self, token: str, reason: str = "stopped") -> None:
        with self._lock:
            if token in self._senders:
                self._drop(token, reason)

    def stop_all(self, reason: str = "stopped by admin") -> None:
        with self._lock:
            for token in list(self._senders):
                self._drop(token, reason)

    # --- screen side ----------------------------------------------------------------
    def screen_events(self, since: int) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        self.screen_seen = time.time()
        with self._lock:
            self._cleanup(time.time())
        events, seq = self.screen.get(since, self.poll_timeout)
        self.screen_seen = time.time()
        return events, seq, self.state()

    def screen_signal(self, to: str, msg: dict[str, Any]) -> None:
        if msg.get("type") not in ("answer", "ice", "resync", "relay-restart"):
            raise ShareError("Unknown message")
        with self._lock:
            active = self._senders.get(self._active or "")
            if not active or active.id != to:
                return  # stale message for a sender that is gone; ignore
            active.mailbox.put(msg)
