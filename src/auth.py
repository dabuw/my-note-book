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
    """Owner session (full access). The demo account is a separate role."""
    return session.get("role") == "user"


def is_demo():
    return session.get("role") == "demo"


def current_role():
    if is_authenticated():
        return "user"
    if is_demo():
        return "demo"
    return "guest"


def demo_password():
    return os.environ.get("DEMO_PASSWORD") or ""


def check_demo_password(candidate):
    """Constant-time check for the public demo password (empty disables demo)."""
    expected = demo_password()
    if not expected or not candidate or not isinstance(candidate, str):
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


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

    if is_demo():
        # 演示账号只能看到演示数据
        return Note.query.filter(Note.is_demo.is_(True))
    if is_authenticated():
        # 真实用户看不到演示数据
        return Note.query.filter(Note.is_demo.is_(False))
    ip = client_ip()
    return Note.query.filter(
        Note.is_demo.is_(False),
        db.or_(Note.is_public.is_(True), Note.author_ip == ip),
    )


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


# --------------------------------------------------------------------------
# Guest AI quota
#
# Guests may try the AI endpoints a few times per day (default 5) so the feature can be
# evaluated without the owner password. The counter is per client IP and kept
# in process: the deployment runs a single gunicorn worker (see
# gunicorn.conf.py), so this is authoritative. With several workers the quota
# would be per worker — acceptable for a demo, documented in DEPLOY.md.
# --------------------------------------------------------------------------

def guest_ai_daily_limit():
    try:
        return max(0, int(os.environ.get("GUEST_AI_DAILY_LIMIT", "5")))
    except (TypeError, ValueError):
        return 5


_ai_usage = {}
_ai_usage_lock = threading.Lock()


def _today():
    return time.strftime("%Y-%m-%d")


def _ai_used_today(ip):
    day, count = _ai_usage.get(ip, (_today(), 0))
    return count if day == _today() else 0


def demo_ai_daily_limit():
    try:
        return max(0, int(os.environ.get("DEMO_AI_DAILY_LIMIT", "20")))
    except (TypeError, ValueError):
        return 20


def ai_quota_remaining():
    """Remaining AI calls for the caller, or None when unlimited (owner)."""
    if is_authenticated():
        return None
    limit = demo_ai_daily_limit() if is_demo() else guest_ai_daily_limit()
    with _ai_usage_lock:
        return max(0, limit - _ai_used_today(client_ip()))


def record_ai_usage():
    """Count one AI call against the guest quota (no-op for the owner)."""
    if is_authenticated():
        return
    ip = client_ip()
    with _ai_usage_lock:
        # Keep the dict from growing forever on a long-running process.
        if len(_ai_usage) > 5000:
            _ai_usage.clear()
        _ai_usage[ip] = (_today(), _ai_used_today(ip) + 1)


def ai_allowed(fn):
    """Allow the owner through, and guests up to their daily AI quota."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        remaining = ai_quota_remaining()
        if remaining is not None and remaining <= 0:
            return (
                jsonify(
                    {
                        "error": "ai_quota_exceeded",
                        "message": "今日 AI 体验次数已用完，输入密码后可无限使用",
                        "ai_quota_remaining": 0,
                    }
                ),
                429,
            )

        response = fn(*args, **kwargs)

        # Only successful calls consume quota, so a failed attempt is free.
        status = response[1] if isinstance(response, tuple) else 200
        if 200 <= status < 300:
            record_ai_usage()
            if isinstance(response, tuple):
                payload = response[0]
                if hasattr(payload, "get_json"):
                    body = payload.get_json() or {}
                    body["ai_quota_remaining"] = ai_quota_remaining()
                    return jsonify(body), status
            return response
        return response

    return wrapper
