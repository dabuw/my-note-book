"""Authentication, role and visibility helpers.

Role model
----------
guest : default, no login. May read notes flagged public plus its own note,
        may create at most GUEST_NOTE_LIMIT note(s), and may only modify or
        delete the note it created itself. Never allowed to publish.
user  : reached by posting the shared password to /api/auth/login.
        Full read/write access and the only role allowed to use AI endpoints.

Client identity
---------------
The application runs behind the host Nginx, which is the single entry point.
Nginx sets `X-Real-IP` to `$remote_addr`, which *overwrites* anything the
client sent, so the header cannot be spoofed.

`X-Forwarded-For` is deliberately NOT used for the quota: Nginx appends to it
via `$proxy_add_x_forwarded_for`, so a client can inject arbitrary entries and
would be able to evade the per-IP limit.
"""

import hmac
import os
import threading
import time
from functools import wraps

from flask import jsonify, request, session

from src.models.user import db


def client_ip():
    """Return the real client IP as seen by the trusted Nginx proxy."""
    return request.headers.get("X-Real-IP") or request.remote_addr or "0.0.0.0"


def is_authenticated():
    return session.get("role") == "user"


def current_role():
    return "user" if is_authenticated() else "guest"


def expected_password():
    return os.environ.get("APP_PASSWORD") or ""


def check_password(candidate):
    """Constant-time password comparison."""
    if not candidate or not isinstance(candidate, str):
        return False
    expected = expected_password()
    if not expected:
        # Refuse to authenticate when no password is configured, rather than
        # silently allowing everything through.
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def guest_note_limit():
    try:
        return max(0, int(os.environ.get("GUEST_NOTE_LIMIT", "1")))
    except (TypeError, ValueError):
        return 1


def login_required(fn):
    """Reject guests with 401 so the frontend can prompt for the password."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            return (
                jsonify(
                    {
                        "error": "auth_required",
                        "message": "该功能需要输入密码后使用",
                    }
                ),
                401,
            )
        return fn(*args, **kwargs)

    return wrapper


def visible_notes_query():
    """Base query already scoped to what the current viewer is allowed to read."""
    from src.models.note import Note

    if is_authenticated():
        return Note.query
    ip = client_ip()
    return Note.query.filter(db.or_(Note.is_public.is_(True), Note.author_ip == ip))


def serialize(note):
    """Serialise a note for the current viewer."""
    return note.to_dict(viewer_ip=client_ip(), role=current_role())


# --------------------------------------------------------------------------
# Very small in-process throttle for password attempts.
# Nginx also applies limit_req on /api/auth/login; this is defence in depth for
# the case where the app is ever reached directly.
# --------------------------------------------------------------------------

_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "10"))
_WINDOW_SECONDS = int(os.environ.get("LOGIN_WINDOW_SECONDS", "300"))
_attempts = {}
_attempts_lock = threading.Lock()


def login_throttled():
    """Return seconds to wait, or 0 when the caller may try a password now."""
    ip = client_ip()
    now = time.time()
    with _attempts_lock:
        hits = [t for t in _attempts.get(ip, []) if now - t < _WINDOW_SECONDS]
        if len(hits) >= _MAX_ATTEMPTS:
            _attempts[ip] = hits
            return int(_WINDOW_SECONDS - (now - hits[0])) + 1
        _attempts[ip] = hits
        return 0


def record_failed_login():
    ip = client_ip()
    now = time.time()
    with _attempts_lock:
        hits = [t for t in _attempts.get(ip, []) if now - t < _WINDOW_SECONDS]
        hits.append(now)
        _attempts[ip] = hits


def clear_login_attempts():
    ip = client_ip()
    with _attempts_lock:
        _attempts.pop(ip, None)
