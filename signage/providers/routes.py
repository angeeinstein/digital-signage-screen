"""Flight route (origin/destination) lookup with a persistent cache.

v1 used OpenSky's *historical* flights for the airframe (2-3 days old) and
cached the result under the current callsign, which produced wrong routes.
v2 looks routes up by callsign:

1. Manual entries (admin panel) always win and never expire.
2. adsbdb.com (free, no key) - callsign route database.
3. AirLabs (optional, needs key, daily budget) as fallback.

Results are cached (found: ``cache_days``, not found: 1 day) and only the
flights actually shown on screen are looked up, a few per poll cycle.
Routes that are geometrically implausible for the aircraft's position are
hidden rather than shown wrong.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

from ..storage import file_lock, read_json, write_json
from ..util import DEFAULT_TIMEOUT, haversine_km

logger = logging.getLogger(__name__)

NOT_FOUND_TTL_S = 24 * 3600
ERROR_RETRY_S = 15 * 60
LOOKUPS_PER_CYCLE = 4
SAVE_DEBOUNCE_S = 30


def _airport(d: dict[str, Any] | None) -> dict[str, Any] | None:
    if not d:
        return None
    return {
        "iata": d.get("iata_code") or "",
        "icao": d.get("icao_code") or "",
        "name": d.get("name") or "",
        "city": d.get("municipality") or "",
        "lat": d.get("latitude"),
        "lon": d.get("longitude"),
    }


def lookup_adsbdb(session: requests.Session, callsign: str) -> dict[str, Any] | None:
    """Return a route dict, ``None`` if unknown. Raises on transport errors."""
    resp = session.get(f"https://api.adsbdb.com/v0/callsign/{callsign}", timeout=DEFAULT_TIMEOUT)
    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        raise RuntimeError("adsbdb rate limit")
    resp.raise_for_status()
    body = resp.json().get("response")
    if not isinstance(body, dict) or "flightroute" not in body:
        return None  # {"response": "unknown callsign"}
    fr = body["flightroute"]
    origin, dest = _airport(fr.get("origin")), _airport(fr.get("destination"))
    if not origin or not dest:
        return None
    return {
        "origin": origin,
        "destination": dest,
        "airline": (fr.get("airline") or {}).get("name") or "",
        "flight_iata": fr.get("callsign_iata") or "",
        "source": "adsbdb",
    }


def lookup_airlabs(session: requests.Session, callsign: str, api_key: str) -> dict[str, Any] | None:
    resp = session.get("https://airlabs.co/api/v9/routes",
                       params={"api_key": api_key, "flight_icao": callsign}, timeout=DEFAULT_TIMEOUT)
    if resp.status_code in (401, 403):
        raise RuntimeError("AirLabs API key rejected")
    if resp.status_code == 429:
        raise RuntimeError("AirLabs rate limit")
    if resp.status_code != 200:
        # Not raise_for_status(): its message contains the URL with the key.
        raise RuntimeError(f"AirLabs answered HTTP {resp.status_code}")
    body = resp.json()
    if body.get("error"):
        raise RuntimeError(f"AirLabs: {body['error'].get('message', 'error')}")
    items = body.get("response") or []
    if not items:
        return None
    r = items[0]
    if not (r.get("dep_iata") or r.get("dep_icao")) or not (r.get("arr_iata") or r.get("arr_icao")):
        return None
    mk = lambda p: {"iata": r.get(f"{p}_iata") or "", "icao": r.get(f"{p}_icao") or "",  # noqa: E731
                    "name": "", "city": "", "lat": None, "lon": None}
    return {"origin": mk("dep"), "destination": mk("arr"), "airline": "",
            "flight_iata": r.get("flight_iata") or "", "source": "airlabs"}


def is_plausible(route: dict[str, Any], lat: float, lon: float) -> bool:
    """Is the aircraft roughly on the way from origin to destination?

    Callsign databases are sometimes outdated (airlines reuse callsigns), so
    we compare the detour via the aircraft's position with the direct route.
    """
    o, d = route.get("origin") or {}, route.get("destination") or {}
    if None in (o.get("lat"), o.get("lon"), d.get("lat"), d.get("lon")):
        return True  # no coordinates (e.g. AirLabs): cannot check
    d_od = haversine_km(o["lat"], o["lon"], d["lat"], d["lon"])
    d_op = haversine_km(o["lat"], o["lon"], lat, lon)
    d_pd = haversine_km(lat, lon, d["lat"], d["lon"])
    if min(d_op, d_pd) < 100:  # near either airport (climb-out, holding, approach)
        return True
    detour = d_op + d_pd - d_od
    return detour <= max(200.0, 0.3 * d_od)


def looks_like_flight_callsign(callsign: str) -> bool:
    """Airline-style callsign (3 letters + digit). Registrations like OEABC are skipped."""
    cs = callsign.strip().upper()
    return 4 <= len(cs) <= 8 and cs[:3].isalpha() and cs[3].isdigit()


class RouteResolver:
    def __init__(self, path: Path, session: requests.Session):
        self.path = path
        self.session = session
        self._lock = threading.Lock()
        self._file_lock = file_lock(path)
        doc = read_json(path, {}) or {}
        if doc.get("version") != 2:
            doc = {}  # v1 cache held unreliable OpenSky data; start fresh
        self._routes: dict[str, dict[str, Any]] = doc.get("routes", {})
        self._usage: dict[str, Any] = doc.get("airlabs_usage", {})
        self._dirty = False
        self._last_save = 0.0

    # --- cache persistence ---------------------------------------------------
    def _save(self, force: bool = False) -> None:
        if not self._dirty or (not force and time.time() - self._last_save < SAVE_DEBOUNCE_S):
            return
        with self._lock:
            doc = {"version": 2, "routes": dict(self._routes), "airlabs_usage": dict(self._usage)}
            self._dirty = False
        with self._file_lock:
            write_json(self.path, doc)
        self._last_save = time.time()

    def flush(self) -> None:
        self._save(force=True)

    # --- admin operations ----------------------------------------------------
    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"callsign": cs, **entry} for cs, entry in sorted(self._routes.items())]

    def set_manual(self, callsign: str, origin: str, destination: str) -> dict[str, Any]:
        cs = callsign.strip().upper()
        mk = lambda code: {"iata": code if len(code) == 3 else "", "icao": code if len(code) == 4 else "",  # noqa: E731
                           "name": "", "city": "", "lat": None, "lon": None}
        entry = {"found": True, "origin": mk(origin.strip().upper()), "destination": mk(destination.strip().upper()),
                 "airline": "", "flight_iata": "", "source": "manual", "fetched_at": time.time()}
        with self._lock:
            self._routes[cs] = entry
            self._dirty = True
        self.flush()
        return {"callsign": cs, **entry}

    def delete(self, callsign: str) -> bool:
        with self._lock:
            removed = self._routes.pop(callsign.strip().upper(), None) is not None
            self._dirty = self._dirty or removed
        self.flush()
        return removed

    def clear(self, keep_manual: bool = True) -> int:
        with self._lock:
            before = len(self._routes)
            self._routes = {k: v for k, v in self._routes.items() if keep_manual and v.get("source") == "manual"}
            self._dirty = True
            removed = before - len(self._routes)
        self.flush()
        return removed

    # --- lookups ---------------------------------------------------------------
    def _fresh(self, entry: dict[str, Any], cache_days: int) -> bool:
        if entry.get("source") == "manual":
            return True
        age = time.time() - entry.get("fetched_at", 0)
        if entry.get("error"):
            return age < ERROR_RETRY_S
        if not entry.get("found"):
            return age < NOT_FOUND_TTL_S
        return age < cache_days * 86400

    def _airlabs_budget_ok(self, limit: int) -> bool:
        today = date.today().isoformat()
        if self._usage.get("date") != today:
            self._usage = {"date": today, "count": 0}
        return self._usage["count"] < limit

    def _lookup(self, callsign: str, cfg: dict[str, Any]) -> dict[str, Any]:
        entry: dict[str, Any] = {"found": False, "fetched_at": time.time()}
        error = None
        try:
            route = lookup_adsbdb(self.session, callsign)
            if route:
                return {**entry, "found": True, **route}
        except Exception as e:
            error = f"adsbdb: {e}"
        if cfg.get("airlabs_enabled") and cfg.get("airlabs_api_key"):
            with self._lock:
                budget_ok = self._airlabs_budget_ok(int(cfg.get("airlabs_daily_limit", 30)))
                if budget_ok:
                    self._usage["count"] += 1
            if budget_ok:
                try:
                    route = lookup_airlabs(self.session, callsign, cfg["airlabs_api_key"])
                    if route:
                        return {**entry, "found": True, **route}
                    error = None
                except Exception as e:
                    error = f"{error}; airlabs: {e}" if error else f"airlabs: {e}"
        if error:
            entry["error"] = error
            logger.info("Route lookup for %s failed: %s", callsign, error)
        return entry

    def annotate(self, flights: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
        """Attach ``route`` to each flight (in place), looking up a few missing ones."""
        if not cfg.get("enabled", True):
            return
        cache_days = int(cfg.get("cache_days", 14))
        budget = LOOKUPS_PER_CYCLE
        for f in flights:
            cs = f.get("callsign") or ""
            if not looks_like_flight_callsign(cs):
                continue
            with self._lock:
                entry = self._routes.get(cs)
            if (entry is None or not self._fresh(entry, cache_days)) and budget > 0:
                budget -= 1
                entry = self._lookup(cs, cfg)
                with self._lock:
                    self._routes[cs] = entry
                    self._dirty = True
            if entry and entry.get("found"):
                route = {k: entry[k] for k in ("origin", "destination", "source") if k in entry}
                if entry.get("source") == "manual" or is_plausible(entry, f["lat"], f["lon"]):
                    f["route"] = route
                    if entry.get("airline"):
                        f["airline"] = entry["airline"]
                    if entry.get("flight_iata"):
                        f["flight_iata"] = entry["flight_iata"]
                else:
                    logger.debug("Hiding implausible route for %s", cs)
        self._save()
