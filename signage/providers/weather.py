"""Current weather. Open-Meteo (free, no key) by default; OpenWeatherMap optional.

Both providers are normalised to the same record so the frontend does not
care which one is used. Units are aviation-friendly: wind in knots, pressure
in hPa (QNH approximation from MSL pressure), visibility in km.
"""

from __future__ import annotations

from typing import Any

import requests

from ..util import DEFAULT_TIMEOUT, KT_PER_MS

# WMO weather interpretation codes -> (description, icon key)
WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "clear"), 1: ("Mainly clear", "clear"), 2: ("Partly cloudy", "partly"),
    3: ("Overcast", "cloudy"), 45: ("Fog", "fog"), 48: ("Freezing fog", "fog"),
    51: ("Light drizzle", "drizzle"), 53: ("Drizzle", "drizzle"), 55: ("Dense drizzle", "drizzle"),
    56: ("Freezing drizzle", "drizzle"), 57: ("Freezing drizzle", "drizzle"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"), 67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 77: ("Snow grains", "snow"),
    80: ("Light showers", "showers"), 81: ("Showers", "showers"), 82: ("Violent showers", "showers"),
    85: ("Snow showers", "snow"), 86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "thunder"), 96: ("Thunderstorm with hail", "thunder"),
    99: ("Thunderstorm with heavy hail", "thunder"),
}

# OpenWeatherMap icon prefix -> icon key
OWM_ICONS = {"01": "clear", "02": "partly", "03": "cloudy", "04": "cloudy", "09": "showers",
             "10": "rain", "11": "thunder", "13": "snow", "50": "fog"}


def _round(v: Any, nd: int = 0) -> Any:
    if not isinstance(v, (int, float)):
        return None
    return round(v, nd) if nd else round(v)


def parse_open_meteo(body: dict[str, Any]) -> dict[str, Any]:
    c = body["current"]
    code = int(c.get("weather_code", -1))
    desc, icon = WMO_CODES.get(code, ("Unknown", "cloudy"))
    vis = c.get("visibility")
    return {
        "provider": "open-meteo",
        "observed_at": c.get("time"),
        "condition": desc,
        "icon": icon,
        "is_day": bool(c.get("is_day", 1)),
        "temp_c": _round(c.get("temperature_2m"), 1),
        "feels_like_c": _round(c.get("apparent_temperature"), 1),
        "dew_point_c": _round(c.get("dew_point_2m"), 1),
        "humidity_pct": _round(c.get("relative_humidity_2m")),
        "pressure_hpa": _round(c.get("pressure_msl")),
        "wind_dir_deg": _round(c.get("wind_direction_10m")),
        "wind_kt": _round(c.get("wind_speed_10m")),
        "gust_kt": _round(c.get("wind_gusts_10m")),
        "visibility_km": _round(vis / 1000, 1) if isinstance(vis, (int, float)) else None,
        "cloud_cover_pct": _round(c.get("cloud_cover")),
    }


def fetch_open_meteo(session: requests.Session, lat: float, lon: float) -> dict[str, Any]:
    resp = session.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,dew_point_2m,pressure_msl,"
                   "wind_speed_10m,wind_direction_10m,wind_gusts_10m,visibility,weather_code,is_day,cloud_cover",
        "wind_speed_unit": "kn", "timezone": "auto",
    }, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return parse_open_meteo(resp.json())


def parse_owm_current(d: dict[str, Any]) -> dict[str, Any]:
    w = (d.get("weather") or [{}])[0]
    main, wind = d.get("main", {}), d.get("wind", {})
    icon = w.get("icon", "03d")
    vis = d.get("visibility")
    temp, hum = main.get("temp"), main.get("humidity")
    dew = None
    if isinstance(temp, (int, float)) and isinstance(hum, (int, float)) and hum > 0:
        dew = round(temp - (100 - hum) / 5, 1)  # Lawrence approximation
    to_kt = lambda v: round(v * KT_PER_MS) if isinstance(v, (int, float)) else None  # noqa: E731
    return {
        "provider": "openweathermap",
        "observed_at": None,
        "condition": (w.get("description") or "").capitalize(),
        "icon": OWM_ICONS.get(icon[:2], "cloudy"),
        "is_day": icon.endswith("d"),
        "temp_c": _round(temp, 1),
        "feels_like_c": _round(main.get("feels_like"), 1),
        "dew_point_c": dew,
        "humidity_pct": _round(hum),
        "pressure_hpa": _round(main.get("pressure")),
        "wind_dir_deg": _round(wind.get("deg")),
        "wind_kt": to_kt(wind.get("speed")),
        "gust_kt": to_kt(wind.get("gust")),
        "visibility_km": _round(vis / 1000, 1) if isinstance(vis, (int, float)) else None,
        "cloud_cover_pct": _round((d.get("clouds") or {}).get("all")),
    }


def fetch_openweathermap(session: requests.Session, lat: float, lon: float, api_key: str) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("OpenWeatherMap API key missing")
    resp = session.get("https://api.openweathermap.org/data/2.5/weather",
                       params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
                       timeout=DEFAULT_TIMEOUT)
    if resp.status_code == 401:
        raise RuntimeError("OpenWeatherMap rejected the API key (new keys take up to 2 h to activate)")
    resp.raise_for_status()
    return parse_owm_current(resp.json())


def fetch_weather(session: requests.Session, cfg: dict[str, Any], lat: float, lon: float) -> dict[str, Any]:
    if cfg.get("provider") == "openweathermap":
        return fetch_openweathermap(session, lat, lon, cfg.get("openweathermap_api_key", ""))
    return fetch_open_meteo(session, lat, lon)
