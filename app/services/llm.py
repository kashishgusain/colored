"""Thin wrapper around an OpenAI-compatible chat API with timeouts and retries."""
import time

from flask import current_app

from .errors import NotConfigured, ServiceError


def llm_configured() -> bool:
    cfg = current_app.config
    return cfg["LLM_PROVIDER"] == "openai" and bool(cfg["OPENAI_API_KEY"])


def translation_configured() -> bool:
    cfg = current_app.config
    return cfg["TRANSLATION_PROVIDER"] == "openai" and bool(cfg["OPENAI_API_KEY"])


def _client():
    cfg = current_app.config
    if not cfg["OPENAI_API_KEY"]:
        raise NotConfigured("OPENAI_API_KEY is not set. Add it to .env (never commit it) and set "
                            "LLM_PROVIDER=openai.", code="LLM_NOT_CONFIGURED")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise NotConfigured("The `openai` package is not installed: pip install openai", code="OPENAI_MISSING") from exc
    return OpenAI(api_key=cfg["OPENAI_API_KEY"], base_url=cfg["OPENAI_BASE_URL"],
                  timeout=cfg["AI_TIMEOUT_SECONDS"], max_retries=0)


def chat(messages: list[dict], json_mode: bool = False, max_tokens: int = 1200, temperature: float = 0.2) -> str:
    """Call the chat model; retries transient failures with exponential backoff."""
    cfg = current_app.config
    client = _client()
    kwargs = {"model": cfg["OPENAI_CHAT_MODEL"], "messages": messages, "max_tokens": max_tokens,
              "temperature": temperature}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    attempts = max(1, cfg["AI_MAX_RETRIES"] + 1)
    last = None
    for i in range(attempts):
        try:
            resp = client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # network, rate limit, auth, timeout ...
            last = exc
            name = type(exc).__name__
            if name in ("AuthenticationError", "PermissionDeniedError", "BadRequestError", "NotFoundError"):
                raise ServiceError(f"The AI provider rejected the request ({name}). Check your API key and model name.",
                                   code="LLM_REJECTED") from exc
            if i < attempts - 1:
                time.sleep(min(2 ** i, 8))
    raise ServiceError(f"The AI provider did not respond after {attempts} attempts ({type(last).__name__}).",
                       code="LLM_UNAVAILABLE", retryable=True) from last
