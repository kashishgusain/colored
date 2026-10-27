"""Speech-to-text. Never fabricates text: if nothing can transcribe, it raises."""
import threading
import time
from pathlib import Path

from flask import current_app

from .errors import NotConfigured, ServiceError

# Whisper has no Garhwali/Kumaoni model. Hindi is the closest supported language,
# so we hint "hi" for these and tell everyone the result is only a rough draft.
LANGUAGE_HINTS = {"hindi": "hi", "english": "en", "garhwali": "hi", "kumaoni": "hi", "jaunsari": "hi", "other": None}
UNSUPPORTED_DIALECTS = {"garhwali", "kumaoni", "jaunsari"}
OPENAI_MAX_BYTES = 25 * 1024 * 1024

_model_cache = {}
_model_lock = threading.Lock()


def provider_name() -> str:
    return current_app.config["TRANSCRIPTION_PROVIDER"]


def dialect_warning(language: str) -> str | None:
    if language in UNSUPPORTED_DIALECTS:
        return ("Speech models do not officially support this language. The transcript was produced with a Hindi "
                "hint and may be inaccurate. A fluent speaker must correct it before approval.")
    return None


def status() -> dict:
    """Health information for the admin dashboard (does not load models)."""
    name = provider_name()
    if name == "none":
        return {"provider": "none", "ready": False,
                "detail": "Disabled. Set TRANSCRIPTION_PROVIDER=faster_whisper (free, local) or openai in .env."}
    if name == "faster_whisper":
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return {"provider": name, "ready": False, "detail": "Package missing: pip install faster-whisper"}
        return {"provider": name, "ready": True,
                "detail": f"Model '{current_app.config['WHISPER_MODEL_SIZE']}' downloads on first use."}
    if name == "openai":
        ok = bool(current_app.config["OPENAI_API_KEY"])
        return {"provider": name, "ready": ok, "detail": "API key present." if ok else "OPENAI_API_KEY is not set."}
    return {"provider": name, "ready": False, "detail": f"Unknown provider '{name}'."}


def transcribe(audio_path: Path, language: str) -> dict:
    """Return {text, language, provider, model}. Raises NotConfigured / ServiceError."""
    name = provider_name()
    hint = LANGUAGE_HINTS.get(language)
    if name == "faster_whisper":
        return _faster_whisper(audio_path, hint)
    if name == "openai":
        return _openai(audio_path, hint)
    raise NotConfigured(
        "No speech-to-text provider is configured, so this recording was not transcribed. "
        "Set TRANSCRIPTION_PROVIDER=faster_whisper (free, runs locally) or TRANSCRIPTION_PROVIDER=openai "
        "with OPENAI_API_KEY in .env, restart the app, then use Retry processing. "
        "You can also type or paste the transcript yourself.", code="TRANSCRIPTION_NOT_CONFIGURED")


def _load_whisper():
    cfg = current_app.config
    key = (cfg["WHISPER_MODEL_SIZE"], cfg["WHISPER_DEVICE"], cfg["WHISPER_COMPUTE_TYPE"])
    with _model_lock:
        if key in _model_cache:
            return _model_cache[key]
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise NotConfigured("faster-whisper is not installed: pip install faster-whisper",
                                code="WHISPER_MISSING") from exc
        try:
            model = WhisperModel(key[0], device=key[1], compute_type=key[2])
        except Exception as exc:
            raise ServiceError(
                f"The Whisper model '{key[0]}' could not be loaded ({type(exc).__name__}). The first run needs "
                "internet access to download the model (from huggingface.co). Check your connection or proxy, "
                "or choose a smaller WHISPER_MODEL_SIZE such as 'base'.", code="WHISPER_MODEL_LOAD_FAILED") from exc
        _model_cache[key] = model
        return model


def _faster_whisper(audio_path: Path, hint):
    model = _load_whisper()
    try:
        segments, info = model.transcribe(str(audio_path), language=hint, vad_filter=True, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments).strip()
    except Exception as exc:
        raise ServiceError(f"Transcription failed ({type(exc).__name__}): {exc}", code="TRANSCRIPTION_FAILED") from exc
    if not text:
        raise ServiceError("No speech was detected in the recording.", code="NO_SPEECH_DETECTED")
    return {"text": text, "language": info.language, "provider": "faster_whisper",
            "model": current_app.config["WHISPER_MODEL_SIZE"]}


def _openai(audio_path: Path, hint):
    from . import media
    from .llm import _client

    cfg = current_app.config
    client = _client()
    path = Path(audio_path)
    if path.stat().st_size > OPENAI_MAX_BYTES:
        path = media.transcode_to_mp3(path, path.with_suffix(".compressed.mp3"))
        if path.stat().st_size > OPENAI_MAX_BYTES:
            raise ServiceError("The audio is longer than the OpenAI upload limit (25 MB) even after compression. "
                               "Use faster_whisper or split the recording.", code="AUDIO_TOO_LONG")
    attempts = max(1, cfg["AI_MAX_RETRIES"] + 1)
    last = None
    for i in range(attempts):
        try:
            with open(path, "rb") as fh:
                kwargs = {"model": cfg["OPENAI_TRANSCRIPTION_MODEL"], "file": fh}
                if hint:
                    kwargs["language"] = hint
                resp = client.audio.transcriptions.create(**kwargs)
            text = (getattr(resp, "text", "") or "").strip()
            if not text:
                raise ServiceError("No speech was detected in the recording.", code="NO_SPEECH_DETECTED")
            return {"text": text, "language": hint, "provider": "openai", "model": cfg["OPENAI_TRANSCRIPTION_MODEL"]}
        except ServiceError:
            raise
        except Exception as exc:
            last = exc
            if type(exc).__name__ in ("AuthenticationError", "PermissionDeniedError", "BadRequestError"):
                raise ServiceError(f"OpenAI rejected the transcription request ({type(exc).__name__}).",
                                   code="TRANSCRIPTION_REJECTED") from exc
            if i < attempts - 1:
                time.sleep(min(2 ** i, 8))
    raise ServiceError(f"OpenAI transcription failed after {attempts} attempts ({type(last).__name__}).",
                       code="TRANSCRIPTION_UNAVAILABLE", retryable=True) from last
