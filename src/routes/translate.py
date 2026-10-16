from flask import Blueprint, jsonify, request

from src.auth import login_required
from src.llm import is_configured, translate

translate_bp = Blueprint('translate', __name__)

# Guard against someone posting a huge body and making the upstream call
# expensive (Nginx already caps the body at 2 MB).
MAX_TRANSLATE_CHARS = 20000


@translate_bp.route('/translate', methods=['POST'])
@login_required
def translate_text():
    """Translate text via the configured LLM.

    Unlike note generation there is no meaningful offline fallback, so an
    unavailable AI service is reported explicitly instead of silently returning
    the original text.
    """
    # Validate the request first: a malformed or oversized request is a client
    # error regardless of whether the AI service happens to be configured.
    data = request.get_json(silent=True) or {}
    text = data.get('text')
    lang = data.get('lang', 'zh-CN')

    if not text or not str(text).strip():
        return jsonify({'error': 'No text provided'}), 400

    if len(text) > MAX_TRANSLATE_CHARS:
        return jsonify({
            'error': 'Text too long (max %d characters)' % MAX_TRANSLATE_CHARS,
            'code': 'text_too_long',
        }), 413

    if not is_configured():
        return jsonify({
            'error': 'AI 未配置：请在服务器 .env 中设置 LLM_API_KEY（或 GITHUB_TOKEN），然后重启容器',
            'code': 'ai_not_configured',
        }), 503

    try:
        translated = translate(text, lang)
        return jsonify({'translation': translated})
    except Exception as e:
        return jsonify({'error': str(e), 'code': 'ai_call_failed'}), 502
