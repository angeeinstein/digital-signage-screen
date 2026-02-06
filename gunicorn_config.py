"""
Gunicorn configuration for Digital Signage Display
Optimized for Raspberry Pi 5
"""

import multiprocessing
import os

# Server socket
bind = "0.0.0.0:80"
backlog = 2048

# Worker processes - optimized for Raspberry Pi 5
# Pi 5 has 4 cores, use 2 workers to leave resources for display
workers = 2
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Max requests per worker before restart (prevent memory leaks)
max_requests = 1000
max_requests_jitter = 50

# Server mechanics
daemon = False
pidfile = "/var/run/digital-signage/gunicorn.pid"
umask = 0
user = None
group = None
tmp_upload_dir = None

# Logging
errorlog = "/var/log/digital-signage/error.log"
loglevel = "info"
accesslog = "/var/log/digital-signage/access.log"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "digital-signage"

# Server hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    print("Starting Digital Signage Server...")


def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    print("Reloading Digital Signage Server...")


def when_ready(server):
    """Called just after the server is started."""
    print(f"Digital Signage Server is ready. Listening on {bind}")


def on_exit(server):
    """Called just before exiting Gunicorn."""
    print("Digital Signage Server shutting down...")
