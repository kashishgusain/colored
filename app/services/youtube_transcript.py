"""YouTube transcript extraction through the configured RapidAPI provider."""
from urllib.parse import parse_qs, urlparse

import httpx
from flask import current_app

from .errors import NotConfigured, ServiceError
from .steps import from_transcript


def _youtube_video_id(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"
    }:
        return None

    if parsed.hostname == "youtu.be":
        return parsed.path.strip("/").split("/", 1)[0] or None

    query_id = parse_qs(parsed.query).get("v", [])
    if query_id and query_id[0]:
        return query_id[0]

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) > 1 and path_parts[0] in {"embed", "live", "shorts"}:
        return path_parts[1]
    return None


def _text_from_payload(payload) -> str:
    """Extract transcript text from the provider's common response shapes."""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list):
        parts = []
        for item in payload:
            if isinstance(item, dict):
                value = item.get("text") or item.get("transcript") or item.get("content")
                if isinstance(value, str):
                    parts.append(value.strip())
            elif isinstance(item, str):
                parts.append(item.strip())
        return " ".join(part for part in parts if part).strip()
    if isinstance(payload, dict):
        for key in ("transcription", "transcript", "text", "content", "data", "result"):
            if key in payload:
                value = _text_from_payload(payload[key])
                if value:
                    return value
    return ""


def extract(url: str) -> dict:
    """Return only source-grounded, ordered knowledge steps."""
    url = (url or "").strip()
    video_id = _youtube_video_id(url)
    if not video_id:
        raise ServiceError("Enter a valid HTTPS YouTube URL.", code="INVALID_YOUTUBE_URL")

    cfg = current_app.config
    if not cfg["RAPIDAPI_KEY"]:
        raise NotConfigured(
            "YouTube transcript extraction is not configured. Set RAPIDAPI_KEY in .env.",
            code="YOUTUBE_TRANSCRIPT_NOT_CONFIGURED",
        )

    headers = {
        "x-rapidapi-host": cfg["YOUTUBE_TRANSCRIPT_API_HOST"],
        "x-rapidapi-key": cfg["RAPIDAPI_KEY"],
    }
    try:
        response = httpx.get(
            cfg["YOUTUBE_TRANSCRIPT_API_URL"],
            headers=headers,
            params={"videoId": video_id},
            timeout=cfg["AI_TIMEOUT_SECONDS"],
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise ServiceError(
            "The YouTube transcript provider rejected the request.",
            code="YOUTUBE_TRANSCRIPT_REJECTED",
            retryable=exc.response.status_code >= 500,
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceError(
            "The YouTube transcript provider is unavailable. Please try again.",
            code="YOUTUBE_TRANSCRIPT_UNAVAILABLE",
            retryable=True,
        ) from exc

    text = _text_from_payload(payload)
    if not text:
        raise ServiceError(
            "The YouTube provider returned no transcript for this video.",
            code="YOUTUBE_TRANSCRIPT_EMPTY",
        )
    extracted = from_transcript(text)
    return {"steps": extracted["steps"], "steps_mode": extracted["mode"]}
