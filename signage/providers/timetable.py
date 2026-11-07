"""Lecture timetable from the FH JOANNEUM "Almaty" JSON API.

Event titles look like (wrapped here)::

    Sustainable Aviation Fuels (-114053) (Vorlesung (VO)), Kraft Gerhard,
        Standardgruppe, ., AP149 AP149.02.201 (LAV 2024)
    Prüfungstermin: B22.0587404 25S 3SSt IL Kunst- und Faserverbundwerkstoffe
        bei Windbacher, -, AP149 AP149.02.212 (LAV 2023)

Start/end are naive local times (Europe/Vienna). The academic year starts in
October; the active cohorts are LAV (bachelor, 3 years) and MAV (master).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests

from ..util import DEFAULT_TIMEOUT

logger = logging.getLogger(__name__)

API_URL = "https://almaty.fh-joanneum.at/stundenplan/json.php"
SOURCE_TZ = ZoneInfo("Europe/Vienna")

ROOM_RE = re.compile(r"\b(AP|EA|ES)\d+[a-z]?\.\w+\.\w+", re.IGNORECASE)
COHORT_RE = re.compile(r"\(([A-Z]{2,4})\s*(\d{4})\)\s*$")
COURSE_RE = re.compile(r"^(.+?)\s*\(-?\d+\)\s*(\([^()]*(?:\([^()]*\))?[^()]*\))?")
KIND_RE = re.compile(r"\(([A-Z]{2,3})\)\)$")
EXAM_RE = re.compile(r"[A-Z]\d+\.\d+\s+\d+[SW]\s+\d+(?:[.,]\d+)?SSt\s+[A-Z]+\s+(.+?)\s+bei\s+")


def academic_year(now: datetime) -> int:
    return now.year if now.month >= 10 else now.year - 1


def default_cohorts(now: datetime) -> list[str]:
    y = academic_year(now)
    return [f"LAV {y - 2}", f"LAV {y - 1}", f"LAV {y}", f"MAV {y - 1}", f"MAV {y}"]


def normalize_cohort(value: str) -> str:
    """'lav2024' / 'LAV 2024' / 'LAV24' -> 'LAV 2024'."""
    m = re.fullmatch(r"\s*([A-Za-z]{2,4})\s*(\d{2}|\d{4})\s*", value)
    if not m:
        return value.strip()
    year = m.group(2)
    if len(year) == 2:
        year = "20" + year
    return f"{m.group(1).upper()} {year}"


def parse_cohorts(value: str, now: datetime) -> list[str]:
    items = [normalize_cohort(v) for v in value.split(",") if v.strip()]
    return items or default_cohorts(now)


def parse_title(title: str) -> dict[str, Any]:
    title = " ".join(title.split())
    room_m = ROOM_RE.search(title)
    room = room_m.group(0).upper() if room_m else ""
    cohort_m = COHORT_RE.search(title)
    cohort = f"{cohort_m.group(1)}{cohort_m.group(2)[-2:]}" if cohort_m else ""
    online = bool(re.search(r",\s*Online\s*(\(|$)", title))

    if title.startswith("Prüfungstermin:"):
        rest = title.removeprefix("Prüfungstermin:").strip()
        m = EXAM_RE.search(rest + " ")
        if m:
            name = m.group(1).strip()
        else:
            name = rest.split(" bei ")[0].strip()
            name = re.sub(r"^[A-Z]\d+\.\d+\s+\d+[SW]\s+\d+(?:[.,]\d+)?SSt\s+[A-Z]+\s+", "", name)
        return {"course": name, "kind": "EXAM", "room": room, "cohort": cohort,
                "online": online, "lecturer": "", "group": ""}

    m = COURSE_RE.match(title)
    if m:
        name = m.group(1).strip()
        kind_m = KIND_RE.search(m.group(2) or "")
        kind = kind_m.group(1) if kind_m else ""
        tail = title[m.end():]
    else:
        name = re.sub(r"\s*\([^)]*\)\s*", " ", title.split(",")[0]).strip()
        kind, tail = "", title[len(title.split(",")[0]):]
    parts = [p.strip() for p in tail.split(",")]
    parts = [p for p in parts if p]
    lecturer = parts[0] if parts else ""
    group = parts[1] if len(parts) > 1 and parts[1] != "Standardgruppe" else ""
    return {"course": name, "kind": kind, "room": room, "cohort": cohort,
            "online": online, "lecturer": lecturer, "group": group}


def _parse_dt(value: str, tz: ZoneInfo) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SOURCE_TZ)
    return dt.astimezone(tz)


def build_lectures(events: list[dict[str, Any]], now: datetime, window_hours: int, show_ongoing: bool,
                   tz: ZoneInfo) -> list[dict[str, Any]]:
    cutoff = now + timedelta(hours=window_hours)
    seen: set[tuple[str, str, str]] = set()
    out = []
    for ev in events:
        start = _parse_dt(ev.get("start", ""), tz)
        if start is None or ev.get("allday"):
            continue
        end = _parse_dt(ev.get("end", ""), tz) or start + timedelta(minutes=90)
        if end <= now or start > cutoff:
            continue
        ongoing = start <= now < end
        if ongoing and not show_ongoing:
            continue
        info = parse_title(ev.get("title", ""))
        key = (start.isoformat(), info["course"], info["room"])
        if key in seen:  # same event listed for several cohorts
            continue
        seen.add(key)
        out.append({
            "id": str(ev.get("id") or "|".join(key)),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "ongoing": ongoing,
            **info,
        })
    out.sort(key=lambda x: x["start"])
    return out


def fetch_lectures(session: requests.Session, cfg: dict[str, Any], tz: ZoneInfo) -> list[dict[str, Any]]:
    now = datetime.now(tz)
    window = int(cfg.get("time_window_hours", 24))
    start = now.date().isoformat()
    end = (now + timedelta(hours=window) + timedelta(days=1)).date().isoformat()
    cohorts = parse_cohorts(cfg.get("cohorts", ""), now)
    events: list[dict[str, Any]] = []
    errors = []
    for cohort in cohorts:
        try:
            resp = session.get(API_URL, params={"q": cohort, "start": start, "end": end}, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                events.extend(data)
        except Exception as e:
            logger.info("Timetable fetch for %s failed: %s", cohort, e)
            errors.append(f"{cohort}: {e}")
    if errors and len(errors) == len(cohorts):
        raise RuntimeError("; ".join(errors))
    lectures = build_lectures(events, now, window, bool(cfg.get("show_ongoing", True)), tz)
    return lectures[: int(cfg.get("max_items", 8))]
