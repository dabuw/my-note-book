"""Vercel serverless entry point (legacy).

This file used to build its own Flask app with an in-memory SQLite fallback,
which silently discarded data on every cold start. It now simply re-exports the
one real application object from `src.main`, so the Docker deployment and any
serverless deployment can never drift apart.

The primary deployment target is the Docker container behind Nginx; see
Dockerfile / docker-compose.yml / gunicorn.conf.py.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

CURRENT_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.main import app  # noqa: E402  (path setup must happen first)

__all__ = ["app"]
