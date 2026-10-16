"""Login / logout / session status endpoints.

The password is only ever read server-side from the APP_PASSWORD environment
variable. It is never rendered into the frontend bundle and never returned by
any endpoint.
"""

from flask import Blueprint, jsonify, request, session

from src.auth import (
    check_password,
    clear_login_attempts,
    current_role,
    guest_note_limit,
    is_authenticated,
    login_throttled,
    record_failed_login,
)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/auth/status", methods=["GET"])
def auth_status():
    return jsonify(
        {
            "role": current_role(),
            "authenticated": is_authenticated(),
            "guest_note_limit": guest_note_limit(),
        }
    )


@auth_bp.route("/auth/login", methods=["POST"])
def login():
    wait = login_throttled()
    if wait:
        return (
            jsonify(
                {
                    "error": "too_many_attempts",
                    "message": f"尝试次数过多，请 {wait} 秒后再试",
                }
            ),
            429,
        )

    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""

    if not check_password(password):
        record_failed_login()
        return jsonify({"error": "invalid_password", "message": "密码错误"}), 401

    clear_login_attempts()
    session.clear()
    session["role"] = "user"
    session.permanent = True
    return jsonify({"role": "user", "authenticated": True})


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"role": "guest", "authenticated": False})
