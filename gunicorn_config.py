"""
Gunicorn configuration for Digital Signage Display
Optimized for Raspberry Pi 5
"""

import multiprocessing
import os

# Server socket
bind = "0.0.0.0:8080"  # Use 8080 to avoid permission issues with port 80
backlog = 2048

# Worker processes - optimized for Raspberry Pi 5
# Pi 5 has 4 cores, use 2 workers to leave resources for display
workers = 2  # Use 2 workers for better performance
worker_class = "sync"
worker_connections = 100  # Reduced from 1000
timeout = 120  # Increased from 30 to prevent worker timeouts
keepalive = 5  # Increased to keep connections alive longer
preload_app = True  # Preload app to speed up worker startup
graceful_timeout = 30  # Time to wait for workers to finish requests during restart

# Max requests per worker before restart (prevent memory leaks)
max_requests = 2000  # Increased from 1000
max_requests_jitter = 100  # Increased jitter

# Server mechanics
daemon = False
pidfile = None  # Let systemd manage the PID
umask = 0
user = None  # Run as the user specified in systemd service
group = None
tmp_upload_dir = None

# Systemd integration
systemd_bind = True  # Use systemd socket activation if available

# Logging - use stdout/stderr for systemd journal
errorlog = "-"  # Log to stderr (systemd captures this)
loglevel = "info"
accesslog = "-"  # Log to stdout (systemd captures this)
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
