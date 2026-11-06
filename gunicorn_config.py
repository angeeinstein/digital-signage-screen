"""Gunicorn configuration.

One worker process with threads: the data pollers and their caches live in
that single process, so every request sees the same data and upstream APIs
are only queried once (v1 ran two workers, each with its own caches).
"""

import os

bind = os.environ.get("SIGNAGE_BIND", "0.0.0.0:8080")
workers = 1
worker_class = "gthread"
threads = 8
timeout = 60
graceful_timeout = 10
keepalive = 5

# Load the app inside the worker (not the master), so the poller threads run
# in the process that serves requests.
preload_app = False

# Files the app creates (settings, credentials) are not world-readable.
umask = 0o027

# Logs go to stdout/stderr -> journald
errorlog = "-"
accesslog = None  # the display polls every few seconds; access logs are noise
loglevel = os.environ.get("SIGNAGE_LOG_LEVEL", "info").lower()
proc_name = "digital-signage"
