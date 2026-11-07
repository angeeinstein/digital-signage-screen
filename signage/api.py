"""JSON API used by the display and the admin panel."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request, session

from . import __version__
from .announcements import AnnouncementError, AnnouncementStore, is_active, problem
from .auth import CredentialStore, LoginThrottle, client_address, login_required
from .config import ConfigError, ConfigStore, admin_view, public_view, validate
from .providers import flights as flights_mod
from .providers import news as news_mod
from .providers import routes as routes_mod
from .providers import timetable as timetable_mod
from .providers import transport as transport_mod
from .providers import weather as weather_mod
from .services import Services

logger = logging.getLogger(__name__)
bp = Blueprint("api", __name__, url_prefix="/api")
_started = time.time()


def _cfg() -> ConfigStore:
    return current_app.extensions["signage.config"]


def _svc() -> Services:
    return current_app.extensions["signage.services"]


def _creds() -> CredentialStore:
    return current_app.extensions["signage.credentials"]


def _throttle() -> LoginThrottle:
    return current_app.extensions["signage.throttle"]


def _ann() -> AnnouncementStore:
    return current_app.extensions["signage.announcements"]


def ok(**data: Any):
    return jsonify({"ok": True, **data})


def fail(message: str, status: int = 400, **data: Any):
    return jsonify({"ok": False, "error": message, **data}), status


def _body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


# --- public -------------------------------------------------------------------------

@bp.get("/health")
def health():
    snap = _svc().snapshot()
    return ok(version=__version__, uptime_s=round(time.time() - _started),
              sources={k: {"status": v["status"], "stale": v["stale"], "updated_at": v["updated_at"]}
                       for k, v in snap.items()})


@bp.get("/display")
def display():
    store = _cfg()
    svc = _svc()
    config = store.get()
    return ok(
        version=__version__,
        build=_build_id(),
        revision=store.revision,
        server_time=datetime.now(timezone.utc).isoformat(),
        config=public_view(config),
        sources={k: v for k, v in svc.snapshot().items() if k != "news"},
        ticker={"speed": config["ticker"]["speed"], "items": svc.ticker_items()},
        slides={
            "items": svc.slides(),
            "every_minutes": config["announcements"]["slide_every_minutes"],
            "seconds": config["announcements"]["slide_seconds"],
            "preview": svc.current_preview(),
        },
    )


def _build_id() -> str:
    """Changes whenever a new frontend is built, so open displays reload themselves."""
    from . import FRONTEND_DIST

    try:
        return str(int((FRONTEND_DIST / "index.html").stat().st_mtime))
    except OSError:
        return "none"


# --- auth -----------------------------------------------------------------------------

@bp.get("/auth/session")
def auth_session():
    creds = _creds()
    if not session.get("logged_in"):
        return ok(logged_in=False)
    return ok(logged_in=True, username=creds.username, must_change=creds.must_change)


@bp.post("/auth/login")
def login():
    key = client_address(request)
    wait = _throttle().retry_after(key)
    if wait:
        return fail(f"Too many failed attempts. Try again in {wait} s.", 429, retry_after=wait)
    data = _body()
    username, password = str(data.get("username", "")), str(data.get("password", ""))
    if not _creds().verify(username, password):
        _throttle().fail(key)
        logger.warning("Failed admin login from %s", key)
        return fail("Invalid username or password", 401)
    _throttle().reset(key)
    session.clear()
    session["logged_in"] = True
    session.permanent = True
    logger.info("Admin login from %s", key)
    return ok(must_change=_creds().must_change)


@bp.post("/auth/logout")
def logout():
    session.clear()
    return ok()


@bp.post("/auth/password")
@login_required
def change_password():
    data = _body()
    try:
        _creds().change(str(data.get("current_password", "")), str(data.get("new_password", "")),
                        (data.get("username") or None))
    except PermissionError as e:
        return fail(str(e), 403)
    except ValueError as e:
        return fail(str(e), 400)
    logger.info("Admin password changed from %s", client_address(request))
    return ok()


# --- admin: config & status -------------------------------------------------------------

@bp.get("/admin/config")
@login_required
def get_config():
    store = _cfg()
    return ok(config=admin_view(store.get()), revision=store.revision)


@bp.put("/admin/config")
@login_required
def put_config():
    try:
        new = _cfg().update(_body().get("config", {}))
    except ConfigError as e:
        return fail(str(e), 422)
    return ok(config=admin_view(new), revision=_cfg().revision)


@bp.get("/admin/status")
@login_required
def status():
    return ok(sources=_svc().snapshot())


@bp.post("/admin/refresh")
@login_required
def refresh():
    _svc().refresh_all()
    return ok()


# --- admin: tests (use unsaved form values) --------------------------------------------

def _draft() -> dict[str, Any]:
    """Current config overlaid with the (unsaved) values from the request.

    Masked secrets in the draft fall back to the stored values.
    """
    from .config import MASK, SECRET_FIELDS

    draft = _body().get("config", {})
    for section, key in SECRET_FIELDS:
        if isinstance(draft.get(section), dict) and draft[section].get(key) == MASK:
            draft[section].pop(key)
    return validate(draft, _cfg().get())


@bp.post("/admin/test/<source>")
@login_required
def test_source(source: str):
    try:
        c = _draft()
    except ConfigError as e:
        return fail(str(e), 422)
    svc = _svc()
    tz = ZoneInfo(c["location"]["timezone"])
    lat, lon = c["location"]["lat"], c["location"]["lon"]
    try:
        if source == "weather":
            w = weather_mod.fetch_weather(svc.session, c["weather"], lat, lon)
            return ok(message=f"{w['condition']}, {w['temp_c']} °C ({w['provider']})", data=w)
        if source == "flights":
            raw, provider = flights_mod.fetch_aircraft(svc.session, c["flights"]["providers"], lat, lon,
                                                       c["flights"]["radius_km"])
            fl = flights_mod.normalize(raw, lat, lon, c["flights"]["radius_km"], c["flights"]["include_ground"])
            return ok(message=f"{len(fl)} aircraft within {c['flights']['radius_km']} km via {provider}")
        if source == "transport":
            if not c["transport"]["stop_id"]:
                return fail("Select a stop first")
            deps = transport_mod.fetch_departures(svc.session, c["transport"]["stop_id"], tz, 5)
            return ok(message=f"{len(deps)} upcoming departures", data=deps)
        if source == "timetable":
            lectures = timetable_mod.fetch_lectures(svc.session, c["timetable"], tz)
            cohorts = timetable_mod.parse_cohorts(c["timetable"]["cohorts"], datetime.now(tz))
            return ok(message=f"{len(lectures)} lectures in the next {c['timetable']['time_window_hours']} h "
                              f"({', '.join(cohorts)})", data=lectures)
        if source == "news":
            headlines, meta = news_mod.fetch_news(svc.session, c["ticker"])
            failed = f", {len(meta['failed'])} feed(s) failed" if meta.get("failed") else ""
            latest = f" Latest: {headlines[0]['title']}" if headlines else ""
            return ok(message=f"{len(headlines)} matching of {meta.get('checked', 0)} headlines from "
                              f"{meta.get('feeds', 0)} feed(s){failed}.{latest}", data=headlines)
        if source == "airlabs":
            key = c["routes"]["airlabs_api_key"]
            if not key:
                return fail("Enter an AirLabs API key first")
            r = routes_mod.lookup_airlabs(svc.session, "DLH400", key)
            sample = f" (DLH400: {r['origin']['iata']} → {r['destination']['iata']})" if r else ""
            return ok(message="API key works" + sample)
    except Exception as e:
        return fail(f"Test failed: {e}", 502)
    return fail("Unknown source", 404)


@bp.get("/admin/stops")
@login_required
def stops():
    q = request.args.get("q", "").strip()[:80]
    c = _cfg().get()
    try:
        results = transport_mod.search_stops(_svc().session, q, (c["location"]["lat"], c["location"]["lon"]),
                                             locality=c["location"]["name"])
    except Exception as e:
        return fail(f"Stop search failed: {e}", 502)
    return ok(stops=results)


# --- admin: route cache ------------------------------------------------------------------

@bp.get("/admin/routes")
@login_required
def list_routes():
    return ok(routes=_svc().routes.list())


@bp.post("/admin/routes")
@login_required
def add_route():
    d = _body()
    cs, o, dest = (str(d.get(k, "")).strip().upper() for k in ("callsign", "origin", "destination"))
    if not cs or len(cs) > 8:
        return fail("Callsign is required (max 8 characters)")
    if len(o) not in (3, 4) or len(dest) not in (3, 4):
        return fail("Origin and destination must be 3-letter IATA or 4-letter ICAO codes")
    entry = _svc().routes.set_manual(cs, o, dest)
    _svc().pollers["flights"].refresh_now()
    return ok(route=entry)


@bp.delete("/admin/routes/<callsign>")
@login_required
def delete_route(callsign: str):
    if not _svc().routes.delete(callsign):
        return fail("Not found", 404)
    return ok()


@bp.delete("/admin/routes")
@login_required
def clear_routes():
    removed = _svc().routes.clear(keep_manual=True)
    return ok(removed=removed)


# --- admin: screen sharing ---------------------------------------------------------------

@bp.get("/admin/share")
@login_required
def share_status():
    hub = current_app.extensions["signage.share"]
    pub = current_app.extensions["signage.public_url"]
    return ok(state=hub.state(), screen_online=hub.screen_online(), public_url=pub.get(),
              detected_url=pub.detected)


@bp.post("/admin/share/stop")
@login_required
def share_stop_all():
    current_app.extensions["signage.share"].stop_all()
    return ok()


# --- admin: announcements ------------------------------------------------------------------

def _with_state(a: dict[str, Any]) -> dict[str, Any]:
    today = datetime.now(ZoneInfo(_cfg().get()["location"]["timezone"])).date()
    return {**a, "active": is_active(a, today), "problem": problem(a)}


@bp.get("/admin/announcements")
@login_required
def list_announcements():
    return ok(announcements=[_with_state(a) for a in _ann().list()])


@bp.post("/admin/announcements")
@login_required
def create_announcement():
    try:
        a = _ann().create(_body())
    except AnnouncementError as e:
        return fail(str(e), 422)
    return ok(announcement=_with_state(a))


@bp.put("/admin/announcements/<ann_id>")
@login_required
def update_announcement(ann_id: str):
    try:
        a = _ann().update(ann_id, _body())
    except AnnouncementError as e:
        return fail(str(e), 422)
    if a is None:
        return fail("Not found", 404)
    return ok(announcement=_with_state(a))


@bp.delete("/admin/announcements/<ann_id>")
@login_required
def delete_announcement(ann_id: str):
    if not _ann().delete(ann_id):
        return fail("Not found", 404)
    return ok()


@bp.post("/admin/announcements/<ann_id>/preview")
@login_required
def preview_announcement(ann_id: str):
    if not _ann().get(ann_id):
        return fail("Not found", 404)
    seconds = _cfg().get()["announcements"]["slide_seconds"]
    _svc().preview(ann_id, seconds)
    return ok(seconds=seconds)


@bp.post("/admin/media")
@login_required
def upload_media():
    from .announcements import MAX_IMAGE_BYTES

    request.max_content_length = MAX_IMAGE_BYTES + 64 * 1024
    file = request.files.get("file")
    if file is None:
        return fail("No file received")
    try:
        name = _ann().save_image(file.stream)
    except AnnouncementError as e:
        return fail(str(e), 422)
    return ok(image=name, url=f"/media/{name}")
