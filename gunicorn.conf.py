"""Gunicorn configuration for the NoteTaker container.

Deliberately a single worker with threads: SQLite allows only one writer at a
time, and the box has 2 vCPU / ~2 GB free. More processes would contend on the
database file and multiply memory use for no benefit at this traffic level.
"""

import os

bind = "0.0.0.0:%s" % os.environ.get("PORT", "5001")

workers = int(os.environ.get("GUNICORN_WORKERS", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"

timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")

# Keep it False: the app runs db.create_all() and sets SQLite pragmas on import,
# which we want to happen inside the worker process.
preload_app = False
