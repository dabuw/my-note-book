"""Login / logout / session status endpoints.

The password is only ever read server-side from the APP_PASSWORD environment
variable. It is never rendered into the frontend bundle and never returned by
any endpoint.
"""

from flask import Blueprint, jsonify, request, session

from src.demo_data import ensure_demo_data
from src.auth import (
    ai_quota_remaining,
    check_demo_password,
    check_password,
    clear_login_attempts,
    current_role,
    guest_note_limit,
    is_authenticated,
    is_demo,
    login_throttled,
    record_failed_login,
)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/auth/status", methods=["GET"])
def auth_status():
    return jsonify(
        {
            "role": current_role(),
            "is_demo": is_demo(),
            "authenticated": is_authenticated(),
            "guest_note_limit": guest_note_limit(),
            "ai_quota_remaining": ai_quota_remaining(),
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

    # 公开的演示账号：只读/可编辑演示数据，看不到真实笔记
    if check_demo_password(password):
        clear_login_attempts()
        session.clear()
        session["role"] = "demo"
        session.permanent = True
        ensure_demo_data()
        return jsonify({"role": "demo", "authenticated": True, "is_demo": True})

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


@auth_bp.route("/demo/reset", methods=["POST"])
def reset_demo():
    """让演示账号手动重置演示数据（每天都自动重置，这里只是方便）。"""
    if not is_demo():
        return jsonify({"error": "forbidden"}), 403
    ensure_demo_data(force=True)
    return jsonify({"ok": True})
