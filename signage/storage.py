"""Small helpers for reading/writing JSON state files safely.

All runtime state (config, credentials, caches, secret key) lives in one
data directory that is ignored by git, so updates via ``git reset`` never
touch it.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def file_lock(path: Path) -> threading.Lock:
    """Return a process-wide lock for ``path`` (one writer at a time)."""
    key = str(path.resolve())
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def read_json(path: Path, default: Any = None) -> Any:
    """Read JSON from ``path``; return ``default`` if missing or corrupt."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as e:
        logger.error("Could not read %s: %s", path, e)
        return default


def write_json(path: Path, data: Any, mode: int = 0o640) -> None:
    """Atomically write ``data`` as JSON to ``path``.

    Writes to a temp file in the same directory and renames it over the
    target, so readers never see a half-written file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, mode)
        except OSError:
            pass  # Not supported on every filesystem (e.g. Windows)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
