"""LLM client.

The endpoint is any OpenAI-compatible chat-completions API. Configuration is
read from the environment, preferring the self-describing `LLM_*` names and
falling back to the older `GITHUB_*` names so existing deployments keep working.

    LLM_BASE_URL   / GITHUB_MODELS_ENDPOINT   base URL, e.g. https://api.deepseek.com/v1
    LLM_API_KEY    / GITHUB_TOKEN             API key for that endpoint
    LLM_MODEL      / GITHUB_MODEL             model name, e.g. deepseek-chat

The API key is only ever read here, server-side. It is never sent to the
frontend and never logged.
"""

import logging
import os
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

load_dotenv()  # Loads environment variables from .env

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://models.github.ai/inference"
DEFAULT_MODEL_NAME = "openai/gpt-4.1-mini"


def _first_env(*names, default=None):
    """Return the first non-empty environment variable among `names`."""
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return default


def llm_api_key():
    return _first_env("LLM_API_KEY", "GITHUB_TOKEN")


def llm_base_url():
    return _first_env("LLM_BASE_URL", "GITHUB_MODELS_ENDPOINT", default=DEFAULT_BASE_URL)


def llm_model():
    return _first_env("LLM_MODEL", "GITHUB_MODEL", default=DEFAULT_MODEL_NAME)


def llm_timeout():
    try:
        return float(_first_env("LLM_TIMEOUT", default="60"))
    except (TypeError, ValueError):
        return 60.0


def is_configured():
    """True when an API key is present, i.e. AI features can be attempted."""
    return bool(llm_api_key())


# Kept as a module-level name because callers import it directly.
DEFAULT_MODEL = llm_model()


def _extract_text(payload: Dict[str, Any]) -> str:
    """Pull the assistant text out of a chat-completions response body."""
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        pass
    try:
        choices = payload.get("choices") or []
        if choices and isinstance(choices[0], dict) and "text" in choices[0]:
            return choices[0]["text"]
    except Exception:
        pass
    raise RuntimeError("Unexpected LLM response format: %r" % (str(payload)[:300],))


def call_llm_model(model: str, messages: List[Dict[str, Any]], temperature: float = 1.0,
                   top_p: float = 1.0) -> str:
    """Call the configured chat-completions endpoint and return the assistant text.

    Raises RuntimeError with an actionable message when the call cannot be made.
    """
    api_key = llm_api_key()
    if not api_key:
        raise RuntimeError(
            "AI 未配置：请在 .env 中设置 LLM_API_KEY（或 GITHUB_TOKEN）"
        )

    base_url = llm_base_url()
    model = model or llm_model()
    timeout = llm_timeout()

    errors = []

    # Path 1: the OpenAI SDK, which every compatible provider speaks.
    try:
        from openai import OpenAI
    except ImportError as exc:
        # Not fatal: path 2 speaks the same protocol. Log it so a broken or
        # missing SDK is visible in the container logs instead of silently
        # changing behaviour.
        logger.warning("openai SDK unavailable, using plain HTTP fallback: %s", exc)
    else:
        try:
            client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
            resp = client.chat.completions.create(
                model=model, messages=messages, temperature=temperature, top_p=top_p
            )
            text = getattr(getattr(resp.choices[0], "message", None), "content", None)
            if text:
                return text
            errors.append("SDK 返回了空内容")
        except Exception as exc:  # noqa: BLE001
            # Covers provider errors AND local SDK problems (e.g. an httpx
            # version mismatch). Path 2 below still gets a chance.
            errors.append(_describe_failure(base_url, model, exc))

    # Path 2: plain HTTP. The request is a single POST to
    # {base_url}/chat/completions, so this works with any OpenAI-compatible
    # provider even when the SDK is missing or broken.
    try:
        resp = requests.post(
            base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": temperature, "top_p": top_p},
            timeout=timeout,
        )
        if resp.ok:
            return _extract_text(resp.json())
        errors.append(
            _describe_failure(
                base_url,
                model,
                RuntimeError("%s %s: %s" % (resp.status_code, resp.reason, resp.text[:300])),
            )
        )
    except Exception as exc:
        errors.append("无法连接 AI 服务 %s: %s" % (base_url, exc))

    # De-duplicate: both paths usually fail for the same underlying reason.
    unique = list(dict.fromkeys(errors)) or ["未知错误"]
    raise RuntimeError(" | ".join(unique))


def _describe_failure(base_url: str, model: str, exc: Exception) -> str:
    """Build a short, actionable error message without leaking the API key."""
    message = str(exc)
    hint = ""
    lowered = message.lower()
    if "401" in message or "unauthorized" in lowered or "invalid api key" in lowered:
        hint = "（API Key 无效或已过期）"
    elif "404" in message or "not found" in lowered:
        hint = "（模型名或 base_url 可能不正确，当前模型：%s）" % model
    elif "429" in message or "rate limit" in lowered:
        hint = "（触发限流，请稍后重试）"
    elif "timeout" in lowered or "timed out" in lowered:
        hint = "（请求超时）"
    elif "connection" in lowered:
        hint = "（网络不可达，请检查服务器出网与 base_url）"
    return "AI 调用失败%s: %s [endpoint=%s, model=%s]" % (
        hint, message[:300], base_url, model
    )


def translate(text: str, target_lang: str = "zh-CN") -> str:
    """Translate `text` into `target_lang` using the configured model."""
    system_prompt = (
        "You are a helpful translator. Translate the user's text into %s. "
        "Return only the translation without extra commentary." % target_lang
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]
    return call_llm_model(DEFAULT_MODEL, messages)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--text", "-t", help="Text to translate", required=False)
    parser.add_argument("--lang", "-l", help="Target language (e.g. zh-CN)", default="zh-CN")
    args = parser.parse_args()

    source = args.text or "Hello, this is a test of the translation feature."
    print("configured:", is_configured(), "| endpoint:", llm_base_url(), "| model:", llm_model())
    try:
        print("Translated:\n", translate(source, args.lang))
    except Exception as e:
        print("Error calling LLM:", e)


if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------
# Note rewriting helpers
# --------------------------------------------------------------------------

REWRITE_MODES = {
    "polish": (
        "You are a Chinese writing assistant. Rewrite the user's note so it reads "
        "as clear, well-structured written Chinese. Keep every fact, name and "
        "number; do not add new information, do not translate, do not prepend a "
        "title. Return only the rewritten note."
    ),
    "summarize": (
        "Summarise the user's note in 2-3 sentences of Chinese. Keep the key facts, "
        "dates and names. Return only the summary, without any prefix like '摘要：'."
    ),
    "todos": (
        "Extract every actionable task from the user's note as a Chinese checklist. "
        "Return one task per line, each line starting with '- [ ] '. If the note "
        "contains no actionable task, return an empty response."
    ),
}


def rewrite(text: str, mode: str = "polish") -> str:
    """Rewrite / summarise / extract todos from `text` using the configured model."""
    system_prompt = REWRITE_MODES.get(mode, REWRITE_MODES["polish"])
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]
    return call_llm_model(DEFAULT_MODEL, messages).strip()
