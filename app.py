#!/usr/bin/env python3
"""WSGI entry point (``gunicorn app:app``) and development server."""

import os

from signage import create_app

app = create_app()

if __name__ == "__main__":
    # Dev server. The Vite dev server (npm run dev) proxies /api here.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True)
