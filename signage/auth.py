"""Admin authentication: password storage, login throttling, request guards."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
import time
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .storage import file_lock, read_json, write_json

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 8
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"


def load_or_create_secret_key(path: Path) -> bytes:
    """Persistent random Flask secret key (never the hard-coded default)."""
    try:
        key = path.read_bytes().strip()
        if len(key) >= 32:
            return key
    except FileNotFoundError:
        pass
    key = secrets.token_hex(32).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    logger.info("Generated new secret key at %s", path)
    return key


class CredentialStore:
    def __init__(self, path: Path, legacy_path: Path | None = None):
        self.path = path
        self._lock = file_lock(path)
        if not path.exists():
            legacy = read_json(legacy_path) if legacy_path else None
            if legacy and legacy.get("username") and legacy.get("password"):
                logger.info("Migrating legacy admin credentials from %s", legacy_path)
                self._save({"username": legacy["username"], "password_hash": legacy["password"], "must_change": False})
            else:
                self._save({
                    "username": DEFAULT_USERNAME,
                    "password_hash": generate_password_hash(DEFAULT_PASSWORD),
                    "must_change": True,
                })
                logger.warning("Created default admin credentials (admin/admin) - change them in the admin panel!")

    def _load(self) -> dict[str, Any]:
        return read_json(self.path, {}) or {}

    def _save(self, data: dict[str, Any]) -> None:
        write_json(self.path, data, mode=0o600)

    @property
    def must_change(self) -> bool:
        return bool(self._load().get("must_change"))

    @property
    def username(self) -> str:
        return self._load().get("username", DEFAULT_USERNAME)

    def verify(self, username: str, password: str) -> bool:
        creds = self._load()
        stored = creds.get("password_hash", "")
        user_ok = hmac.compare_digest(str(username), str(creds.get("username", "")))
        if _is_legacy_sha256(stored):
            # v1 stored an unsalted SHA-256; accept once and upgrade.
            pw_ok = hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)
            if user_ok and pw_ok:
                with self._lock:
                    creds["password_hash"] = generate_password_hash(password)
                    creds["must_change"] = password == DEFAULT_PASSWORD
                    self._save(creds)
                logger.info("Upgraded legacy password hash")
        else:
            pw_ok = bool(stored) and check_password_hash(stored, password)
        return user_ok and pw_ok

    def change(self, current: str, new: str, new_username: str | None = None) -> None:
        creds = self._load()
        if not self.verify(creds.get("username", ""), current):
            raise PermissionError("Current password is incorrect")
        if len(new) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
        if new == DEFAULT_PASSWORD:
            raise ValueError("Please choose a password other than the default")
        with self._lock:
            creds = self._load()
            creds["password_hash"] = generate_password_hash(new)
            creds["must_change"] = False
            if new_username:
                creds["username"] = new_username.strip()
            self._save(creds)


def _is_legacy_sha256(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


class LoginThrottle:
    """Simple in-memory limiter: N failed attempts per IP per window."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 300):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        items = [t for t in self._failures.get(key, []) if now - t < self.window]
        self._failures[key] = items
        return items

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            items = self._recent(key, now)
            if len(items) < self.max_failures:
                return 0
            return int(self.window - (now - items[0])) + 1

    def fail(self, key: str) -> None:
        with self._lock:
            self._recent(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


def login_required(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"ok": False, "error": "Not authenticated"}), 401
        return fn(*args, **kwargs)
    return wrapper


CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "signage"


def csrf_protect() -> Any:
    """Reject state-changing requests without our custom header.

    Browsers cannot send custom headers cross-origin without a CORS preflight
    (which we never allow), so this blocks cross-site form/fetch attacks.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            return jsonify({"ok": False, "error": "Missing request header"}), 403
    return None
