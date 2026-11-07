"""Public transport via the Austrian TRIAS API (Verbund Linie, no key needed).

Lessons from v1 kept here:

* Requests are TRIAS 1.2 XML; responses use the ``trias:`` namespace.
* Times are UTC (``...Z``); we convert to the configured local time zone.
* Querying a stop area id (``at:46:1234``) returns departures from all its
  platforms (``at:46:1234:0:1`` ...).
* Name search can return few results; a coordinate search around the
  configured location fills the gap.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests

from ..util import DEFAULT_TIMEOUT

logger = logging.getLogger(__name__)

TRIAS_URL = "http://ogdtrias.verbundlinie.at:8183/stv/trias"
NS = {"trias": "http://www.vdv.de/trias", "siri": "http://www.siri.org.uk/siri"}
T = f"{{{NS['trias']}}}"
S = f"{{{NS['siri']}}}"
REQUESTOR = "digital_signage"


def _sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    el = ET.SubElement(parent, T + tag)
    if text is not None:
        el.text = text
    return el


def build_request(payload_builder) -> bytes:
    """Build a TRIAS ServiceRequest; ``payload_builder(RequestPayload)`` adds the body."""
    ET.register_namespace("", NS["trias"])
    ET.register_namespace("siri", NS["siri"])
    root = ET.Element(T + "Trias", {"version": "1.2"})
    sr = _sub(root, "ServiceRequest")
    ts = ET.SubElement(sr, S + "RequestTimestamp")
    ts.text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ref = ET.SubElement(sr, S + "RequestorRef")
    ref.text = REQUESTOR
    payload_builder(_sub(sr, "RequestPayload"))
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")


def _post(session: requests.Session, body: bytes) -> ET.Element:
    resp = session.post(TRIAS_URL, data=body, headers={"Content-Type": "text/xml; charset=utf-8"},
                        timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def _text(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path, NS)
    return found.text.strip() if found is not None and found.text else None


def _error_code(root: ET.Element) -> str | None:
    return _text(root, ".//trias:ErrorMessage/trias:Text/trias:Text")


# --- stop search -----------------------------------------------------------------

def location_request_by_name(query: str, limit: int) -> bytes:
    def build(p: ET.Element) -> None:
        lir = _sub(p, "LocationInformationRequest")
        name = _sub(_sub(lir, "InitialInput"), "LocationName")
        _sub(name, "Text", query)
        _sub(name, "Language", "de")
        r = _sub(lir, "Restrictions")
        _sub(r, "Type", "stop")
        _sub(r, "NumberOfResults", str(limit))
    return build_request(build)


def location_request_by_coords(lat: float, lon: float, radius_m: int, limit: int) -> bytes:
    def build(p: ET.Element) -> None:
        lir = _sub(p, "LocationInformationRequest")
        circle = _sub(_sub(_sub(lir, "InitialInput"), "GeoRestriction"), "Circle")
        centre = _sub(circle, "Center")
        _sub(centre, "Longitude", f"{lon:.6f}")
        _sub(centre, "Latitude", f"{lat:.6f}")
        _sub(circle, "Radius", str(radius_m))
        r = _sub(lir, "Restrictions")
        _sub(r, "Type", "stop")
        _sub(r, "NumberOfResults", str(limit))
    return build_request(build)


def parse_locations(root: ET.Element) -> list[dict[str, Any]]:
    """Parse LocationInformationResponse into unique stops (by id)."""
    stops: dict[str, dict[str, Any]] = {}
    for loc in root.iterfind(".//trias:Location", NS):
        sp = loc.find("trias:StopPoint", NS)
        sa = loc.find("trias:StopPlace", NS)
        if sp is not None:
            sid, name = _text(sp, "trias:StopPointRef"), _text(sp, "trias:StopPointName/trias:Text")
        elif sa is not None:
            sid, name = _text(sa, "trias:StopPlaceRef"), _text(sa, "trias:StopPlaceName/trias:Text")
        else:
            continue
        if not sid or not name:
            continue
        locality = _text(loc, "trias:LocationName/trias:Text") or ""
        lat = _text(loc, "trias:GeoPosition/trias:Latitude")
        lon = _text(loc, "trias:GeoPosition/trias:Longitude")
        stops.setdefault(sid, {
            "stop_id": sid,
            "name": name,
            "locality": locality,
            "lat": float(lat) if lat else None,
            "lon": float(lon) if lon else None,
        })
    return list(stops.values())


def _norm(text: str) -> str:
    t = text.lower().replace("ß", "ss").replace("straße", "str").replace("strasse", "str")
    return "".join(ch if ch.isalnum() else " " for ch in t)


def _matches(query: str, name: str) -> bool:
    n = _norm(name)
    return all(tok in n for tok in _norm(query).split())


def search_stops(session: requests.Session, query: str, near: tuple[float, float] | None = None,
                 locality: str = "", limit: int = 15) -> list[dict[str, Any]]:
    """Find stops by name, preferring ones close to ``near``.

    The TRIAS name search is fuzzy across all of Austria and often misses
    without a town name ("Alte Poststraße" finds nothing useful, "Graz Alte
    Poststraße" works). So we combine: plain name search, name search
    prefixed with the configured locality, and stops within 5 km whose name
    matches. With an empty query, nearby stops are returned.
    """
    from ..util import haversine_km

    found: dict[str, dict[str, Any]] = {}
    requests_to_make: list[bytes] = []
    if query:
        requests_to_make.append(location_request_by_name(query, limit))
        if locality and locality.lower() not in query.lower():
            requests_to_make.append(location_request_by_name(f"{locality} {query}", limit))
    if near:
        requests_to_make.append(location_request_by_coords(near[0], near[1], 5000, 100))
    errors = []
    for i, body in enumerate(requests_to_make):
        try:
            stops = parse_locations(_post(session, body))
        except Exception as e:
            errors.append(str(e))
            continue
        is_nearby = near is not None and i == len(requests_to_make) - 1
        for s in stops:
            if is_nearby and query and not _matches(query, s["name"]):
                continue
            found.setdefault(s["stop_id"], s)
    if errors and not found:
        raise RuntimeError("; ".join(errors))
    results = list(found.values())
    if near:
        for s in results:
            s["distance_km"] = (round(haversine_km(near[0], near[1], s["lat"], s["lon"]), 1)
                                if s["lat"] is not None else None)
        results.sort(key=lambda s: (s["distance_km"] is None, s["distance_km"] or 0))
    return results[:limit]


# --- departures -------------------------------------------------------------------

def departures_request(stop_id: str, limit: int) -> bytes:
    def build(p: ET.Element) -> None:
        ser = _sub(p, "StopEventRequest")
        _sub(_sub(_sub(ser, "Location"), "LocationRef"), "StopPointRef", stop_id)
        params = _sub(ser, "Params")
        _sub(params, "NumberOfResults", str(limit))
        _sub(params, "StopEventType", "departure")
        _sub(params, "IncludeRealtimeData", "true")
    return build_request(build)


def _parse_time(value: str | None, tz: ZoneInfo) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def parse_departures(root: ET.Element, tz: ZoneInfo) -> list[dict[str, Any]]:
    out = []
    for ev in root.iterfind(".//trias:StopEvent", NS):
        dep = ev.find("trias:ThisCall/trias:CallAtStop/trias:ServiceDeparture", NS)
        planned = _parse_time(_text(dep, "trias:TimetabledTime"), tz)
        estimated = _parse_time(_text(dep, "trias:EstimatedTime"), tz)
        if planned is None and estimated is None:
            continue
        service = ev.find("trias:Service", NS)
        line = _text(service, ".//trias:PublishedLineName/trias:Text") or "?"
        dest = _text(service, "trias:DestinationText/trias:Text") or ""
        mode = (_text(service, ".//trias:Mode/trias:PtMode") or "bus").lower()
        cancelled = (_text(service, "trias:Cancelled") or "").lower() == "true" \
            or (_text(ev, "trias:ThisCall/trias:CallAtStop/trias:NotServicedStop") or "").lower() == "true"
        platform = _text(ev, "trias:ThisCall/trias:CallAtStop/trias:PlannedBay/trias:Text")
        best = estimated or planned
        delay_min = None
        if estimated and planned:
            delay_min = round((estimated - planned).total_seconds() / 60)
        out.append({
            "line": line,
            "destination": dest,
            "mode": mode,
            "platform": platform,
            "planned": planned.isoformat() if planned else None,
            "expected": best.isoformat(),
            "realtime": estimated is not None,
            "delay_min": delay_min,
            "cancelled": cancelled,
        })
    out.sort(key=lambda d: d["expected"])
    return out


def fetch_departures(session: requests.Session, stop_id: str, tz: ZoneInfo, limit: int) -> list[dict[str, Any]]:
    root = _post(session, departures_request(stop_id, limit))
    err = _error_code(root)
    deps = parse_departures(root, tz)
    if err and not deps:
        if err == "STOPEVENT_LOCATIONUNSERVED":
            return []  # no service right now (e.g. at night)
        raise RuntimeError(f"TRIAS: {err}")
    now = datetime.now(tz)
    return [d for d in deps if datetime.fromisoformat(d["expected"]) >= now.replace(second=0, microsecond=0)][:limit]
