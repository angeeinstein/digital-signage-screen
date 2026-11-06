"""Live aircraft positions from community ADS-B aggregators.

All supported providers serve the readsb/tar1090 JSON format, so one parser
handles them. They are tried in the configured order; the first that answers
wins. Lessons from v1:

* airplanes.live now answers 403 to API clients that have not registered, which
  is why the v1 flight list was empty so often. It is kept as the last fallback.
* ``dst`` in these APIs is in nautical miles (v1 displayed it as km). We
  compute distance ourselves from lat/lon instead.
* ``alt_baro`` is the string ``"ground"`` for aircraft on the ground.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from ..aircraft import HELICOPTER_ICON, aircraft_icon, airline_from_callsign, is_christophorus
from ..util import DEFAULT_TIMEOUT, KM_PER_NM, bearing_deg, haversine_km

logger = logging.getLogger(__name__)

PROVIDER_URLS = {
    "adsb.lol": "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}",
    "adsb.fi": "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{nm}",
    "airplanes.live": "https://api.airplanes.live/v2/point/{lat}/{lon}/{nm}",
}

MAX_POSITION_AGE_S = 60  # ignore aircraft whose last position is older


class ProviderError(Exception):
    pass


def fetch_aircraft(session: requests.Session, providers: list[str], lat: float, lon: float,
                   radius_km: float) -> tuple[list[dict[str, Any]], str]:
    """Fetch raw aircraft from the first working provider. Returns (aircraft, provider)."""
    nm = max(1, min(250, round(radius_km / KM_PER_NM)))
    errors = []
    for name in providers:
        url = PROVIDER_URLS[name].format(lat=round(lat, 4), lon=round(lon, 4), nm=nm)
        try:
            resp = session.get(url, timeout=DEFAULT_TIMEOUT)
            if resp.status_code != 200:
                raise ProviderError(f"HTTP {resp.status_code}")
            body = resp.json()
            aircraft = body.get("ac", body.get("aircraft"))
            if not isinstance(aircraft, list):
                raise ProviderError("unexpected response format")
            return aircraft, name
        except (requests.RequestException, ValueError, ProviderError) as e:
            logger.info("Flight provider %s failed: %s", name, e)
            errors.append(f"{name}: {e}")
    raise ProviderError("; ".join(errors) or "no providers configured")


def normalize(raw: list[dict[str, Any]], lat: float, lon: float, radius_km: float,
              include_ground: bool = False) -> list[dict[str, Any]]:
    """Turn raw readsb records into display records, nearest first."""
    out: dict[str, dict[str, Any]] = {}
    for ac in raw:
        a_lat, a_lon = ac.get("lat"), ac.get("lon")
        if a_lat is None or a_lon is None:
            a_lat, a_lon = (ac.get("lastPosition") or {}).get("lat"), (ac.get("lastPosition") or {}).get("lon")
        if a_lat is None or a_lon is None:
            continue
        if (ac.get("seen_pos") or 0) > MAX_POSITION_AGE_S:
            continue
        alt = ac.get("alt_baro")
        on_ground = alt == "ground"
        if on_ground and not include_ground:
            continue
        distance = haversine_km(lat, lon, a_lat, a_lon)
        if distance > radius_km:
            continue

        hex_id = (ac.get("hex") or "").lower().lstrip("~")
        callsign = (ac.get("flight") or "").strip().upper()
        registration = (ac.get("r") or "").strip().upper()
        type_code = (ac.get("t") or "").strip().upper()
        emitter = ac.get("category")
        if not type_code and is_christophorus(callsign):
            type_code = "H135"  # ÖAMTC Christophorus fleet (H135/EC135)
        icon = aircraft_icon(type_code, emitter)
        if is_christophorus(callsign):
            icon = HELICOPTER_ICON
        airline_code, airline_name = airline_from_callsign(callsign)

        record = {
            "id": hex_id or callsign or registration,
            "hex": hex_id,
            "callsign": callsign,
            "registration": registration,
            "type": type_code,
            "type_name": (ac.get("desc") or "").strip().title(),
            "icon": icon,
            "airline_code": airline_code,
            "airline": airline_name,
            "lat": round(a_lat, 5),
            "lon": round(a_lon, 5),
            "altitude_ft": None if on_ground or not isinstance(alt, (int, float)) else int(alt),
            "on_ground": on_ground,
            "vertical_rate_fpm": ac.get("baro_rate", ac.get("geom_rate")),
            "speed_kt": round(ac["gs"]) if isinstance(ac.get("gs"), (int, float)) else None,
            "track_deg": round(ac["track"]) if isinstance(ac.get("track"), (int, float)) else None,
            "distance_km": round(distance, 1),
            "bearing_deg": round(bearing_deg(lat, lon, a_lat, a_lon)),
            "squawk": ac.get("squawk"),
            "emergency": ac.get("emergency") not in (None, "none"),
            "route": None,
        }
        # Some feeds list the same airframe twice (e.g. ADS-B + MLAT); keep the closer.
        key = record["id"]
        if key and (key not in out or out[key]["distance_km"] > record["distance_km"]):
            out[key] = record
    return sorted(out.values(), key=lambda r: r["distance_km"])
