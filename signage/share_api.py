"""HTTP endpoints for screen sharing (see share.py for the overall flow)."""

from __future__ import annotations

import logging
import re
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, Response, current_app, jsonify, request

from .auth import client_address
from .share import ShareError, ShareHub, is_local_screen

logger = logging.getLogger(__name__)
bp = Blueprint("share", __name__, url_prefix="/api/share")

MAX_CHUNK_BYTES = 4 * 1024 * 1024
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _hub() -> ShareHub:
    return current_app.extensions["signage.share"]


def _settings() -> dict[str, Any]:
    return current_app.extensions["signage.config"].get()["share"]


def _body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _fail(message: str, status: int):
    return jsonify({"ok": False, "error": message}), status


def enabled_only(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _settings()["enabled"]:
            return _fail("Screen sharing is turned off", 404)
        try:
            return fn(*args, **kwargs)
        except ShareError as e:
            return _fail(str(e), e.status)
    return wrapper


def screen_only(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_local_screen(request.environ, request.headers):
            return _fail("Only the screen itself can receive", 403)
        return fn(*args, **kwargs)
    return wrapper


# --- laptop (sender) -------------------------------------------------------------------

@bp.get("/info")
def info():
    s = _settings()
    return jsonify({"ok": True, "enabled": s["enabled"], "relay": s["relay_enabled"],
                    "screen_online": s["enabled"] and _hub().screen_online(),
                    "email": access_email(request)})


@bp.post("/request")
@enabled_only
def share_request():
    name = str(_body().get("name", "")).strip() or access_email(request)
    r = _hub().request(name, client_address(request))
    return jsonify({"ok": True, **r})


def access_email(req: Any) -> str:
    """The e-mail address Cloudflare Access logged the visitor in with, if any.

    Only trusted for requests that arrived through the local tunnel
    (cloudflared on this machine), like ``client_address``.
    """
    if req.remote_addr not in ("127.0.0.1", "::1"):
        return ""
    return req.headers.get("Cf-Access-Authenticated-User-Email", "").strip()[:80]


@bp.post("/verify")
@enabled_only
def share_verify():
    d = _body()
    r = _hub().verify(str(d.get("token", "")), str(d.get("code", "")), limit_s=_settings()["max_minutes"] * 60)
    return jsonify({"ok": True, **r, "relay": _settings()["relay_enabled"]})


@bp.post("/extend")
@enabled_only
def share_extend():
    msg = _hub().extend(str(_body().get("token", "")))
    return jsonify({"ok": True, **msg})


@bp.post("/signal")
@enabled_only
def share_signal():
    d = _body()
    msg = d.get("message")
    if not isinstance(msg, dict):
        return _fail("message missing", 400)
    if msg.get("type") == "relay" and not _settings()["relay_enabled"]:
        return _fail("Sharing through the internet is turned off; connect to the local network", 403)
    _hub().sender_signal(str(d.get("token", "")), msg)
    return jsonify({"ok": True})


@bp.get("/events")
@enabled_only
def share_events():
    events, seq = _hub().sender_events(request.args.get("token", ""), request.args.get("since", 0, type=int))
    return jsonify({"ok": True, "events": events, "seq": seq})


@bp.post("/relay")
@enabled_only
def share_relay():
    if not _settings()["relay_enabled"]:
        return _fail("Sharing through the internet is turned off", 403)
    session = request.args.get("session", "")
    if not SESSION_RE.match(session):
        return _fail("bad session", 400)
    request.max_content_length = MAX_CHUNK_BYTES
    data = request.get_data(cache=False)
    _hub().relay_put(request.args.get("token", ""), session, request.args.get("seq", -1, type=int), data)
    return jsonify({"ok": True})


@bp.post("/stop")
@enabled_only
def share_stop():
    _hub().stop(str(_body().get("token", "")))
    return jsonify({"ok": True})


# --- the TV (receiver) -------------------------------------------------------------------

@bp.get("/screen/events")
@screen_only
@enabled_only
def screen_events():
    events, seq, state = _hub().screen_events(request.args.get("since", 0, type=int))
    return jsonify({"ok": True, "events": events, "seq": seq, "state": state,
                    "public_url": current_app.extensions["signage.public_url"].get()})


@bp.post("/screen/signal")
@screen_only
@enabled_only
def screen_signal():
    d = _body()
    msg = d.get("message")
    if not isinstance(msg, dict):
        return _fail("message missing", 400)
    _hub().screen_signal(str(d.get("to", "")), msg)
    return jsonify({"ok": True})


@bp.get("/screen/relay")
@screen_only
@enabled_only
def screen_relay():
    kind, seq, data = _hub().relay.get(request.args.get("session", ""), request.args.get("after", -1, type=int),
                                     min(15, _hub().poll_timeout))
    if kind == "chunk":
        resp = Response(data, mimetype="application/octet-stream")
        resp.headers["X-Seq"] = str(seq)
        resp.headers["Cache-Control"] = "no-store"
        return resp
    if kind == "wait":
        return Response(status=204)
    return _fail(kind, 409)  # "gap" (fell behind) or "gone" (stream ended)
