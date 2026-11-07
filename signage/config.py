"""Dashboard configuration: defaults, validation, migration and persistence."""

from __future__ import annotations

import copy
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .storage import file_lock, read_json, write_json

logger = logging.getLogger(__name__)

CONFIG_VERSION = 2

# Keys whose values are secrets: never sent to the public display endpoint and
# masked in the admin UI.
SECRET_FIELDS: list[tuple[str, str]] = [
    ("weather", "openweathermap_api_key"),
    ("routes", "airlabs_api_key"),
]

FLIGHT_PROVIDERS = ["adsb.lol", "adsb.fi", "airplanes.live"]
WEATHER_PROVIDERS = ["open-meteo", "openweathermap"]
TICKER_SPEEDS = ["slow", "normal", "fast"]

# Free RSS feeds that answer automated clients (AvHerald has no public feed,
# Aviation Safety Network blocks bots).
DEFAULT_NEWS_FEEDS = "\n".join([
    "https://www.austrianwings.info/feed.rss",
    "https://www.flightglobal.com/feed/",
])
# Only headlines containing one of these are shown (case-insensitive, also
# inside words, so "absturz" matches "Flugzeugabsturz"). Empty = all headlines.
DEFAULT_NEWS_KEYWORDS = ("crash, accident, emergency landing, incident, fatal, killed, "
                         "absturz, unfall, notlandung, zwischenfall, tote")

DEFAULTS: dict[str, Any] = {
    "location": {
        "name": "Graz",
        "lat": 47.0707,
        "lon": 15.4395,
        "timezone": "Europe/Vienna",
    },
    "display": {
        "font_scale": 1.0,
        "map_enabled": True,
        "map_zoom": 8.5,
    },
    "weather": {
        "enabled": True,
        "provider": "open-meteo",  # free, no key needed
        "openweathermap_api_key": "",
        "refresh_seconds": 600,
    },
    "flights": {
        "enabled": True,
        "providers": list(FLIGHT_PROVIDERS),  # tried in order, failover on error
        "radius_km": 75,
        "max_items": 6,
        "include_ground": False,
        "refresh_seconds": 15,
    },
    "routes": {
        "enabled": True,
        "cache_days": 14,
        "airlabs_enabled": False,
        "airlabs_api_key": "",
        "airlabs_daily_limit": 30,  # free tier is 1000/month
    },
    "transport": {
        "enabled": True,
        "stop_id": "",
        "stop_name": "",
        "max_items": 8,
        "refresh_seconds": 60,
    },
    "timetable": {
        "enabled": True,
        "cohorts": "",  # comma separated, e.g. "LAV 2024, MAV 2025"; empty = automatic
        "max_items": 8,
        "time_window_hours": 24,
        "show_ongoing": True,
        "refresh_seconds": 300,
    },
    "ticker": {
        "enabled": False,
        "speed": "normal",
        "emergencies": True,  # squawk 7500/7600/7700 in range
        "notable_aircraft": True,  # rare types and military aircraft in range
        "news_enabled": True,
        "news_feeds": DEFAULT_NEWS_FEEDS,
        "news_keywords": DEFAULT_NEWS_KEYWORDS,
        "news_max_age_hours": 24,
        "news_max_items": 5,
        "refresh_seconds": 900,
    },
    "announcements": {
        "slides_enabled": True,
        "slide_every_minutes": 5,
        "slide_seconds": 15,
    },
}


# --- validation ---------------------------------------------------------------

class ConfigError(ValueError):
    pass


def _num(lo: float, hi: float, integer: bool = False) -> Callable[[Any], Any]:
    def check(v: Any) -> Any:
        if isinstance(v, bool):
            raise ConfigError("expected a number")
        try:
            n = int(v) if integer else float(v)
        except (TypeError, ValueError):
            raise ConfigError("expected a number") from None
        if not lo <= n <= hi:
            raise ConfigError(f"must be between {lo} and {hi}")
        return n
    return check


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    raise ConfigError("expected true/false")


def _str(max_len: int = 200) -> Callable[[Any], str]:
    def check(v: Any) -> str:
        if v is None:
            return ""
        if not isinstance(v, str):
            raise ConfigError("expected text")
        v = v.strip()
        if len(v) > max_len:
            raise ConfigError(f"must be at most {max_len} characters")
        return v
    return check


def _choice(options: list[str]) -> Callable[[Any], str]:
    def check(v: Any) -> str:
        if v not in options:
            raise ConfigError(f"must be one of {', '.join(options)}")
        return v
    return check


def _providers(v: Any) -> list[str]:
    if not isinstance(v, list) or not v:
        raise ConfigError("select at least one provider")
    out = []
    for p in v:
        if p not in FLIGHT_PROVIDERS:
            raise ConfigError(f"unknown provider {p!r}")
        if p not in out:
            out.append(p)
    return out


def _feeds(v: Any) -> str:
    v = _str(2000)(v)
    urls = [u.strip() for u in v.splitlines() if u.strip()]
    for u in urls:
        if not u.startswith(("http://", "https://")) or " " in u:
            raise ConfigError(f"not a web address: {u[:60]}")
    if len(urls) > 10:
        raise ConfigError("at most 10 feeds")
    return "\n".join(urls)


def _timezone(v: Any) -> str:
    from zoneinfo import ZoneInfo

    v = _str(64)(v)
    try:
        ZoneInfo(v)
    except Exception:
        raise ConfigError("unknown time zone") from None
    return v


SCHEMA: dict[str, dict[str, Callable[[Any], Any]]] = {
    "location": {
        "name": _str(80),
        "lat": _num(-90, 90),
        "lon": _num(-180, 180),
        "timezone": _timezone,
    },
    "display": {
        "font_scale": _num(0.5, 2.0),
        "map_enabled": _bool,
        "map_zoom": _num(3, 14),
    },
    "weather": {
        "enabled": _bool,
        "provider": _choice(WEATHER_PROVIDERS),
        "openweathermap_api_key": _str(100),
        "refresh_seconds": _num(60, 3600, integer=True),
    },
    "flights": {
        "enabled": _bool,
        "providers": _providers,
        "radius_km": _num(5, 250, integer=True),
        "max_items": _num(1, 20, integer=True),
        "include_ground": _bool,
        "refresh_seconds": _num(5, 300, integer=True),
    },
    "routes": {
        "enabled": _bool,
        "cache_days": _num(1, 90, integer=True),
        "airlabs_enabled": _bool,
        "airlabs_api_key": _str(100),
        "airlabs_daily_limit": _num(0, 1000, integer=True),
    },
    "transport": {
        "enabled": _bool,
        "stop_id": _str(100),
        "stop_name": _str(120),
        "max_items": _num(1, 20, integer=True),
        "refresh_seconds": _num(30, 600, integer=True),
    },
    "timetable": {
        "enabled": _bool,
        "cohorts": _str(200),
        "max_items": _num(1, 30, integer=True),
        "time_window_hours": _num(1, 168, integer=True),
        "show_ongoing": _bool,
        "refresh_seconds": _num(60, 3600, integer=True),
    },
    "ticker": {
        "enabled": _bool,
        "speed": _choice(TICKER_SPEEDS),
        "emergencies": _bool,
        "notable_aircraft": _bool,
        "news_enabled": _bool,
        "news_feeds": _feeds,
        "news_keywords": _str(500),
        "news_max_age_hours": _num(1, 168, integer=True),
        "news_max_items": _num(1, 20, integer=True),
        "refresh_seconds": _num(300, 3600, integer=True),
    },
    "announcements": {
        "slides_enabled": _bool,
        "slide_every_minutes": _num(1, 120, integer=True),
        "slide_seconds": _num(5, 120, integer=True),
    },
}


def validate(partial: Any, base: dict[str, Any]) -> dict[str, Any]:
    """Validate ``partial`` (possibly incomplete) and merge it onto ``base``.

    Unknown sections/keys are ignored. Raises ConfigError with a field path.
    """
    if not isinstance(partial, dict):
        raise ConfigError("configuration must be an object")
    result = copy.deepcopy(base)
    for section, fields in SCHEMA.items():
        incoming = partial.get(section)
        if incoming is None:
            continue
        if not isinstance(incoming, dict):
            raise ConfigError(f"{section}: expected an object")
        for key, check in fields.items():
            if key not in incoming:
                continue
            try:
                result[section][key] = check(incoming[key])
            except ConfigError as e:
                raise ConfigError(f"{section}.{key}: {e}") from None
    return result


def merge_defaults(data: dict[str, Any]) -> dict[str, Any]:
    """Return a full config: defaults overlaid with valid values from ``data``.

    Invalid stored values are dropped field by field (and logged) instead of
    breaking the whole dashboard.
    """
    result = copy.deepcopy(DEFAULTS)
    for section, fields in SCHEMA.items():
        stored = data.get(section)
        if not isinstance(stored, dict):
            continue
        for key, check in fields.items():
            if key in stored:
                try:
                    result[section][key] = check(stored[key])
                except ConfigError as e:
                    logger.warning("Ignoring invalid config value %s.%s: %s", section, key, e)
    return result


def migrate_v1(old: dict[str, Any]) -> dict[str, Any]:
    """Convert the v1 ``dashboard_config.json`` layout to the current schema."""
    new: dict[str, Any] = {}
    loc = old.get("location") or {}
    new["location"] = {k: loc[k] for k in ("name", "lat", "lon") if k in loc}
    disp = old.get("display") or {}
    if "font_scale" in disp:
        new["display"] = {"font_scale": disp["font_scale"]}
    w = old.get("weather") or {}
    new["weather"] = {"enabled": w.get("enabled", True)}
    if w.get("api_key"):
        new["weather"].update(provider="openweathermap", openweathermap_api_key=w["api_key"])
    fl = old.get("airlabs") or {}
    new["flights"] = {k2: fl[k1] for k1, k2 in (("enabled", "enabled"), ("radius_km", "radius_km")) if k1 in fl}
    r_old = old.get("airlabs_route") or {}
    new["routes"] = {}
    if r_old.get("api_key"):
        new["routes"].update(airlabs_enabled=bool(r_old.get("enabled", True)), airlabs_api_key=r_old["api_key"])
    tr = old.get("transport") or {}
    new["transport"] = {k: tr[k] for k in ("enabled", "stop_id", "stop_name") if k in tr}
    tt = old.get("timetable") or {}
    new["timetable"] = {k: tt[k] for k in ("enabled", "max_items", "time_window_hours") if k in tt}
    if tt.get("cohort"):
        new["timetable"]["cohorts"] = tt["cohort"]
    return new


def public_view(config: dict[str, Any]) -> dict[str, Any]:
    """Config without secrets, safe for unauthenticated clients."""
    view = copy.deepcopy(config)
    for section, key in SECRET_FIELDS:
        view.get(section, {}).pop(key, None)
    return view


MASK = "••••••••"


def admin_view(config: dict[str, Any]) -> dict[str, Any]:
    """Config for the admin UI: secrets replaced by a mask if set."""
    view = copy.deepcopy(config)
    for section, key in SECRET_FIELDS:
        if view.get(section, {}).get(key):
            view[section][key] = MASK
    return view


class ConfigStore:
    """Thread-safe access to the persisted configuration."""

    def __init__(self, path: Path, legacy_path: Path | None = None):
        self.path = path
        self._lock = file_lock(path)
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._cache: dict[str, Any] | None = None
        self._meta_lock = threading.Lock()
        self._load(legacy_path)

    def _load(self, legacy_path: Path | None) -> None:
        raw = read_json(self.path)
        if raw is None and legacy_path is not None and legacy_path.exists():
            legacy = read_json(legacy_path, {})
            logger.info("Migrating legacy config from %s", legacy_path)
            raw = {"data": migrate_v1(legacy)}
            self._write(merge_defaults(raw["data"]), revision=1)
            return
        if raw is None:
            self._write(copy.deepcopy(DEFAULTS), revision=1)
            return
        self._cache = {
            "revision": int(raw.get("revision", 1)),
            "updated_at": raw.get("updated_at"),
            "data": merge_defaults(raw.get("data") or {}),
        }

    def _write(self, data: dict[str, Any], revision: int) -> None:
        doc = {
            "version": CONFIG_VERSION,
            "revision": revision,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        write_json(self.path, doc)
        self._cache = doc

    def get(self) -> dict[str, Any]:
        assert self._cache is not None
        return copy.deepcopy(self._cache["data"])

    @property
    def revision(self) -> int:
        assert self._cache is not None
        return self._cache["revision"]

    def update(self, partial: dict[str, Any]) -> dict[str, Any]:
        """Validate and persist a (partial) config update. Masked secrets are kept."""
        partial = copy.deepcopy(partial)
        for section, key in SECRET_FIELDS:
            if isinstance(partial.get(section), dict) and partial[section].get(key) == MASK:
                partial[section].pop(key)
        with self._lock:
            new = validate(partial, self.get())
            self._write(new, revision=self.revision + 1)
        for fn in list(self._listeners):
            try:
                fn(new)
            except Exception:
                logger.exception("Config listener failed")
        return copy.deepcopy(new)

    def on_change(self, fn: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.append(fn)
