"""Ticker items: live events from our own aircraft data, news and announcements.

The ticker is optional. Everything here is cheap and in-memory; only the
news feeds are fetched by a poller (see services.py).
"""

from __future__ import annotations

import threading
import time
from typing import Any

# Types worth pointing out to aviation students when they pass by.
NOTABLE_TYPES: dict[str, str] = {
    "A388": "Airbus A380",
    "A124": "Antonov An-124",
    "A225": "Antonov An-225",
    "AN22": "Antonov An-22",
    "A3ST": "Airbus Beluga",
    "A337": "Airbus BelugaXL",
    "BLCF": "Boeing 747 Dreamlifter",
    "B741": "Boeing 747-100", "B742": "Boeing 747-200", "B743": "Boeing 747-300",
    "B744": "Boeing 747-400", "B748": "Boeing 747-8",
    "C17": "Boeing C-17 Globemaster", "C5M": "Lockheed C-5 Galaxy",
    "A400": "Airbus A400M", "K35R": "Boeing KC-135",
    "E3TF": "Boeing E-3 AWACS", "E3CF": "Boeing E-3 AWACS",
    "B52": "Boeing B-52", "CONC": "Concorde", "IL76": "Ilyushin Il-76", "IL96": "Ilyushin Il-96",
    "B377": "Boeing Stratocruiser", "DC3": "Douglas DC-3", "JU52": "Junkers Ju 52",
    "U2": "Lockheed U-2",
}

COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# How long an event stays in the ticker after the aircraft was last seen.
LINGER_S = {"emergency": 15 * 60, "aircraft": 5 * 60}


def compass(bearing: float | None) -> str:
    if bearing is None:
        return ""
    return COMPASS[int((bearing % 360) / 45 + 0.5) % 8]


def _where(f: dict[str, Any]) -> str:
    parts = [f"{f['distance_km']:.0f} km {compass(f.get('bearing_deg'))}".strip()]
    if f.get("on_ground"):
        parts.append("on the ground")
    elif f.get("altitude_ft") is not None:
        parts.append(f"{f['altitude_ft']:,} ft")
    return " · ".join(parts)


def _label(f: dict[str, Any]) -> str:
    return f.get("callsign") or f.get("registration") or (f.get("hex") or "").upper()


def aircraft_event(f: dict[str, Any], emergencies: bool, notable: bool) -> dict[str, Any] | None:
    """Ticker event for one aircraft, or None if it is not remarkable."""
    if emergencies and f.get("emergency"):
        kind = f.get("emergency_kind") or "emergency"
        what = f"squawk {f['squawk']}" if f.get("squawk") else "declared"
        type_ = f" ({f['type']})" if f.get("type") else ""
        return {
            "kind": "emergency",
            "text": f"{_label(f)}{type_}: {kind}, {what} · {_where(f)}",
        }
    if not notable:
        return None
    type_code = (f.get("type") or "").upper()
    if type_code in NOTABLE_TYPES:
        return {"kind": "aircraft", "text": f"Rare visitor: {NOTABLE_TYPES[type_code]} {_label(f)} · {_where(f)}"}
    if f.get("military"):
        name = f.get("type_name") or f.get("type") or "aircraft"
        return {"kind": "aircraft", "text": f"Military: {name} {_label(f)} · {_where(f)}"}
    return None


class AircraftEvents:
    """Remembers remarkable aircraft for a while after they leave the area."""

    def __init__(self) -> None:
        self._events: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def update(self, flights: list[dict[str, Any]], emergencies: bool, notable: bool,
               now: float | None = None) -> None:
        now = now or time.time()
        with self._lock:
            for f in flights:
                ev = aircraft_event(f, emergencies, notable)
                if not ev:
                    continue
                key = f"{f['id']}:{ev['kind']}"
                prev = self._events.get(key)
                self._events[key] = {**ev, "id": key, "first_seen": prev["first_seen"] if prev else now,
                                     "last_seen": now}
            self._expire(now)

    def _expire(self, now: float) -> None:
        for key in [k for k, e in self._events.items() if now - e["last_seen"] > LINGER_S[e["kind"]]]:
            del self._events[key]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def items(self, now: float | None = None) -> list[dict[str, Any]]:
        with self._lock:
            self._expire(now or time.time())
            events = sorted(self._events.values(), key=lambda e: (e["kind"] != "emergency", -e["first_seen"]))
            return [{"id": e["id"], "kind": e["kind"], "text": e["text"]} for e in events]
