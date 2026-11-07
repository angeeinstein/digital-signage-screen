"""Announcements: event invitations and notices, shown as full-screen slides
and/or in the ticker, optionally with a poster image.

Stored in ``data/announcements.json``; images in ``data/media/``.
"""

from __future__ import annotations

import copy
import logging
import re
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from .storage import read_json, write_json

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_ANNOUNCEMENTS = 50
MEDIA_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|webp|gif)$")

# Detected from the file's first bytes, never from its name. SVG is not
# accepted because it can contain scripts.
_SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
]


class AnnouncementError(ValueError):
    pass


def image_type(head: bytes) -> str | None:
    for sig, ext in _SIGNATURES:
        if head.startswith(sig):
            return ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _text(v: Any, max_len: int, field: str) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        raise AnnouncementError(f"{field}: expected text")
    v = v.strip()
    if len(v) > max_len:
        raise AnnouncementError(f"{field}: at most {max_len} characters")
    return v


def _date(v: Any, field: str) -> str:
    v = _text(v, 10, field)
    if not v:
        return ""
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise AnnouncementError(f"{field}: expected a date (YYYY-MM-DD)") from None


def validate(data: Any, base: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AnnouncementError("expected an object")
    a = copy.deepcopy(base) if base else {
        "title": "", "text": "", "image": "", "start_date": "", "end_date": "",
        "in_ticker": True, "as_slide": True, "enabled": True,
    }
    if "title" in data:
        a["title"] = _text(data["title"], 120, "Title")
    if "text" in data:
        a["text"] = _text(data["text"], 600, "Text")
    if "image" in data:
        img = _text(data["image"], 64, "Image")
        if img and not MEDIA_NAME_RE.match(img):
            raise AnnouncementError("Image: unknown file")
        a["image"] = img
    for key in ("start_date", "end_date"):
        if key in data:
            a[key] = _date(data[key], key.replace("_", " ").capitalize())
    for key in ("in_ticker", "as_slide", "enabled"):
        if key in data:
            if not isinstance(data[key], bool):
                raise AnnouncementError(f"{key}: expected true/false")
            a[key] = data[key]
    if not a["title"] and not a["image"]:
        raise AnnouncementError("Enter a title or add an image")
    if a["start_date"] and a["end_date"] and a["end_date"] < a["start_date"]:
        raise AnnouncementError("The end date is before the start date")
    if not a["in_ticker"] and not a["as_slide"]:
        raise AnnouncementError("Show it as a slide, in the ticker, or both")
    return a


def is_active(a: dict[str, Any], today: date) -> bool:
    if not a.get("enabled", True):
        return False
    d = today.isoformat()
    if a.get("start_date") and d < a["start_date"]:
        return False
    if a.get("end_date") and d > a["end_date"]:
        return False
    return True


class AnnouncementStore:
    def __init__(self, path: Path, media_dir: Path):
        self.path = path
        self.media_dir = media_dir
        self._lock = threading.Lock()
        raw = read_json(path, {}) or {}
        self._items: list[dict[str, Any]] = [i for i in raw.get("items", []) if isinstance(i, dict) and i.get("id")]

    def _save(self) -> None:
        write_json(self.path, {"version": 1, "items": self._items})

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._items)

    def active(self, today: date) -> list[dict[str, Any]]:
        return [a for a in self.list() if is_active(a, today)]

    def get(self, ann_id: str) -> dict[str, Any] | None:
        with self._lock:
            return copy.deepcopy(next((a for a in self._items if a["id"] == ann_id), None))

    def create(self, data: Any) -> dict[str, Any]:
        a = validate(data)
        self._check_image(a["image"])
        now = datetime.now(timezone.utc).isoformat()
        a.update(id=uuid.uuid4().hex[:12], created_at=now, updated_at=now)
        with self._lock:
            if len(self._items) >= MAX_ANNOUNCEMENTS:
                raise AnnouncementError(f"At most {MAX_ANNOUNCEMENTS} announcements; delete old ones first")
            self._items.append(a)
            self._save()
        return copy.deepcopy(a)

    def update(self, ann_id: str, data: Any) -> dict[str, Any] | None:
        with self._lock:
            idx = next((i for i, a in enumerate(self._items) if a["id"] == ann_id), None)
            if idx is None:
                return None
            old = self._items[idx]
            a = validate(data, old)
            self._check_image(a["image"])
            a["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._items[idx] = a
            self._save()
        self._remove_unused_media()
        return copy.deepcopy(a)

    def delete(self, ann_id: str) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = [a for a in self._items if a["id"] != ann_id]
            if len(self._items) == before:
                return False
            self._save()
        self._remove_unused_media()
        return True

    def _check_image(self, name: str) -> None:
        if name and not (self.media_dir / name).is_file():
            raise AnnouncementError("Image not found; upload it again")

    def save_image(self, stream: BinaryIO) -> str:
        """Store an uploaded image under a random name and return the name."""
        head = stream.read(16)
        ext = image_type(head)
        if not ext:
            raise AnnouncementError("Only PNG, JPEG, WebP or GIF images are supported")
        self.media_dir.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.{ext}"
        target = self.media_dir / name
        size = len(head)
        try:
            with open(target, "wb") as f:
                f.write(head)
                while chunk := stream.read(256 * 1024):
                    size += len(chunk)
                    if size > MAX_IMAGE_BYTES:
                        raise AnnouncementError(f"Image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
                    f.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        self._remove_unused_media(keep=name)
        return name

    def _remove_unused_media(self, keep: str | None = None) -> None:
        """Delete images no announcement uses (older than an hour, so fresh
        uploads that are not saved yet survive)."""
        if not self.media_dir.is_dir():
            return
        used = {a["image"] for a in self.list() if a.get("image")}
        cutoff = datetime.now().timestamp() - 3600
        for f in self.media_dir.iterdir():
            if f.name in used or f.name == keep or not MEDIA_NAME_RE.match(f.name):
                continue
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError as e:
                logger.warning("Could not remove unused image %s: %s", f, e)
