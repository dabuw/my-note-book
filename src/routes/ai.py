"""AI rewriting endpoints: polish, summarise and todo extraction.

The model itself is configured in src/llm.py; this module only validates the
request, applies the guest AI quota (see src/auth.py) and shapes the response.
"""

from flask import Blueprint, jsonify, request

from src.auth import ai_allowed
from src.llm import REWRITE_MODES, is_configured, rewrite

ai_bp = Blueprint("ai", __name__)

# Same guard as the translation endpoint: Nginx caps the body at 2 MB, this
# keeps a single request from turning into an expensive upstream call.
MAX_REWRITE_CHARS = 8000


@ai_bp.route("/ai/rewrite", methods=["POST"])
@ai_allowed
def rewrite_text():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    mode = (data.get("mode") or "polish").strip()

    if not text:
        return jsonify({"error": "No text provided"}), 400
    if len(text) > MAX_REWRITE_CHARS:
        return jsonify({"error": "text_too_long", "message": "内容过长，请分段处理"}), 400
    if mode not in REWRITE_MODES:
        return jsonify({"error": "invalid_mode", "message": "不支持的改写类型"}), 400
    if not is_configured():
        return jsonify({"error": "ai_not_configured", "message": "AI 未配置：请检查 LLM_API_KEY"}), 503

    try:
        result = rewrite(text, mode)
    except Exception as exc:  # network / upstream / auth failure
        return jsonify({"error": "ai_failed", "message": "AI 处理失败：%s" % exc}), 502

    return jsonify({"result": result, "mode": mode})
