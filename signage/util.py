"""Shared helpers: HTTP session and geo maths."""

from __future__ import annotations

import math
import re

import requests
from requests.adapters import HTTPAdapter

USER_AGENT = "digital-signage-screen/2.0 (+https://github.com/angeeinstein/digital-signage-screen)"
DEFAULT_TIMEOUT = (5, 10)  # connect, read

EARTH_RADIUS_KM = 6371.0
KM_PER_NM = 1.852
FT_PER_M = 3.28084
KT_PER_MS = 1.943844


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# Query parameters that carry API keys (OpenWeatherMap: appid, AirLabs: api_key).
_SECRET_PARAM_RE = re.compile(r"(?i)\b(appid|api_?key|key|token|access_token|secret)=([^&\s'\")]+)")


def redact_secrets(text: str) -> str:
    """Hide API keys in URLs inside error messages (requests puts the full URL in them)."""
    return _SECRET_PARAM_RE.sub(lambda m: f"{m.group(1)}=***", text)
