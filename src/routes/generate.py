from flask import Blueprint, jsonify, request
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.auth import login_required
from src.call_llm_model import process_user_notes

generate_bp = Blueprint('generate', __name__)


@generate_bp.route('/generate-notes', methods=['POST'])
@login_required
def generate_notes():
    """Turn free-form text into a structured note.

    Request JSON:
        {"user_input": "...", "language": "Chinese"|"English"}

    Response JSON:
        {"title", "content", "tags", "event_date", "event_time",
         "ai_used": bool, "warning": str|omitted}

    When the LLM is unavailable (no API key, network error, bad model name) the
    note is still produced by the local date/time parser and returned with
    HTTP 200 plus `ai_used: false` and a `warning`, so the feature degrades
    instead of breaking. Only unexpected server-side faults return 5xx.
    """
    data = request.get_json(silent=True) or {}
    user_input = data.get('user_input')
    language = data.get('language', 'Chinese')

    if not user_input or not str(user_input).strip():
        return jsonify({'error': 'No user_input provided'}), 400

    try:
        result = process_user_notes(language, user_input)

        response = {
            "title": result.get("Title", ""),
            "content": result.get("Notes", ""),
            "tags": result.get("Tags", []),
            "event_date": result.get("Event_Date", None),
            "event_time": result.get("Event_Time", None),
            "ai_used": bool(result.get("ai_used", False)),
        }
        if result.get("warning"):
            response["warning"] = result["warning"]
        if result.get("ai_used") is None:
            response["ai_used"] = False

        return jsonify(response)
    except Exception as e:
        return jsonify({'error': 'Note generation failed: %s' % str(e)}), 500
