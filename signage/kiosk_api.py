"""Endpoints for the kiosk agent (local only) and the admin "Screen" page."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import Blueprint, Response, current_app, jsonify, request

from .auth import login_required
from .kiosk import COMMANDS, MAX_SCREENSHOT_BYTES, KioskHub
from .share import is_local_screen

bp = Blueprint("kiosk", __name__)


def _hub() -> KioskHub:
    return current_app.extensions["signage.kiosk"]


def _fail(message: str, status: int):
    return jsonify({"ok": False, "error": message}), status


def local_only(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_local_screen(request.environ, request.headers):
            return _fail("Only the agent on this machine may call this", 403)
        return fn(*args, **kwargs)
    return wrapper


# --- agent (runs in the Pi's desktop session) ----------------------------------------------

@bp.get("/api/kiosk/agent/commands")
@local_only
def agent_commands():
    info: dict[str, Any] = {k[5:]: v for k, v in request.args.items() if k.startswith("info_")}
    r = _hub().agent_poll(request.args.get("since", 0, type=int), info)
    return jsonify({"ok": True, **r})


@bp.post("/api/kiosk/agent/screenshot")
@local_only
def agent_screenshot():
    request.max_content_length = MAX_SCREENSHOT_BYTES
    data = request.get_data(cache=False)
    if not data:
        return _fail("empty", 400)
    _hub().store_screenshot(data, request.content_type or "image/jpeg")
    return jsonify({"ok": True})


@bp.post("/api/kiosk/agent/screenshot-error")
@local_only
def agent_screenshot_error():
    data = request.get_json(silent=True) or {}
    _hub().store_screenshot_error(str(data.get("error", "unknown error")))
    return jsonify({"ok": True})


# --- admin --------------------------------------------------------------------------------------

@bp.get("/api/admin/kiosk")
@login_required
def kiosk_status():
    svc = current_app.extensions["signage.services"]
    return jsonify({"ok": True, **_hub().status(), "heartbeat": svc.pollers["heartbeat"].to_dict()})


@bp.post("/api/admin/kiosk/<action>")
@login_required
def kiosk_action(action: str):
    hub = _hub()
    if action == "reload":
        hub.request_reload()
        return jsonify({"ok": True, "message": "The display reloads within a few seconds."})
    if action not in COMMANDS:
        return _fail("Unknown action", 404)
    if not hub.agent_online():
        return _fail("The kiosk helper on the Pi isn't running (see README: kiosk setup).", 409)
    hub.queue(action)
    messages = {
        "restart-browser": "The browser restarts within a few seconds.",
        "reboot": "The Pi restarts now. The dashboard is back in about a minute.",
        "screenshot": "Taking a screenshot…",
    }
    return jsonify({"ok": True, "message": messages[action]})


@bp.get("/api/admin/kiosk/screenshot")
@login_required
def kiosk_screenshot():
    hub = _hub()
    if not hub.screenshot:
        return _fail("No screenshot yet", 404)
    resp = Response(hub.screenshot, mimetype=hub.screenshot_type)
    resp.headers["Cache-Control"] = "no-store"
    return resp
