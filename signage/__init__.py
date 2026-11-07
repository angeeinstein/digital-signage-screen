"""Digital signage dashboard for aviation students."""

from __future__ import annotations

import atexit
import logging
import os
from datetime import timedelta
from pathlib import Path

from flask import Flask, abort, send_from_directory

__version__ = "2.1.0"

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
STATIC_DIR = BASE_DIR / "static"

logger = logging.getLogger(__name__)


def create_app(data_dir: str | os.PathLike | None = None, start_pollers: bool | None = None) -> Flask:
    from .announcements import MEDIA_NAME_RE, AnnouncementStore
    from .api import bp as api_bp
    from .auth import CredentialStore, LoginThrottle, csrf_protect, load_or_create_secret_key
    from .config import ConfigStore
    from .providers.routes import RouteResolver
    from .services import Services
    from .util import make_session

    logging.basicConfig(level=os.environ.get("SIGNAGE_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    data = Path(data_dir or os.environ.get("SIGNAGE_DATA_DIR") or BASE_DIR / "data")
    data.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    app.config.update(
        SECRET_KEY=load_or_create_secret_key(data / "secret_key"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_NAME="signage_session",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=256 * 1024,
        JSON_SORT_KEYS=False,
    )

    # Legacy (v1) files lived next to app.py; migrate them on first start.
    config = ConfigStore(data / "config.json", legacy_path=_legacy(data, "dashboard_config.json"))
    credentials = CredentialStore(data / "auth.json", legacy_path=_legacy(data, "admin_auth.json"))
    routes = RouteResolver(data / "route_cache.json", make_session())
    media_dir = data / "media"
    announcements = AnnouncementStore(data / "announcements.json", media_dir)
    services = Services(config, routes, announcements)

    app.extensions.update({
        "signage.config": config,
        "signage.credentials": credentials,
        "signage.throttle": LoginThrottle(),
        "signage.services": services,
        "signage.announcements": announcements,
    })

    if os.environ.get("SIGNAGE_BEHIND_PROXY") == "1":
        # Behind nginx: use X-Forwarded-For so login throttling sees real clients.
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]

    app.before_request(csrf_protect)
    app.register_blueprint(api_bp)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if resp.mimetype == "text/html":
            resp.headers.setdefault("X-Frame-Options", "DENY")
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    # --- frontend (built React app) -------------------------------------------------
    @app.get("/assets/<path:filename>")
    def assets(filename: str):
        resp = send_from_directory(FRONTEND_DIST / "assets", filename, max_age=31536000)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp

    @app.get("/")
    @app.get("/admin")
    @app.get("/admin/<path:_sub>")
    @app.get("/login")
    def spa(_sub: str | None = None):
        if not (FRONTEND_DIST / "index.html").exists():
            return ("<h1>Frontend not built</h1><p>Run <code>npm ci &amp;&amp; npm run build</code> "
                    "in the <code>frontend/</code> directory.</p>", 503)
        return send_from_directory(FRONTEND_DIST, "index.html")

    @app.get("/media/<name>")
    def media(name: str):
        # Uploaded announcement images (random names, type checked on upload).
        if not MEDIA_NAME_RE.match(name):
            abort(404)
        return send_from_directory(media_dir, name, max_age=86400)

    @app.get("/favicon.svg")
    def favicon():
        if not (FRONTEND_DIST / "favicon.svg").exists():
            abort(404)
        return send_from_directory(FRONTEND_DIST, "favicon.svg")

    if start_pollers is None:
        start_pollers = os.environ.get("SIGNAGE_DISABLE_POLLERS") != "1"
    if start_pollers:
        services.start()
        atexit.register(services.stop)

    return app


def _legacy(data_dir: Path, name: str) -> Path | None:
    for candidate in (data_dir / "legacy" / name, BASE_DIR / name):
        if candidate.exists():
            return candidate
    return None
