"""Central configuration. All secrets come from environment variables (.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    APP_ENV = "development"
    SECRET_KEY = os.environ.get("SECRET_KEY") or None  # generated in dev if missing

    INSTANCE_DIR = BASE_DIR / "instance"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + (BASE_DIR / "instance" / "lokvaani.db").as_posix()
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- uploads -----------------------------------------------------------
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER") or str(BASE_DIR / "uploads")
    MAX_CONTENT_LENGTH = _int("MAX_UPLOAD_MB", 250) * 1024 * 1024
    MAX_SIZE_BY_KIND = {
        "audio": _int("MAX_AUDIO_MB", 100) * 1024 * 1024,
        "video": _int("MAX_VIDEO_MB", 200) * 1024 * 1024,
        "photo": 10 * 1024 * 1024,
        "document": 10 * 1024 * 1024,
    }

    # --- security ------------------------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_TIME_LIMIT = 3600 * 8
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    # --- processing ----------------------------------------------------------
    PROCESSING_SYNC = False  # True => run jobs inline (tests)
    PROCESSING_WORKERS = _int("PROCESSING_WORKERS", 2)
    FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")
    FFMPEG_TIMEOUT = _int("FFMPEG_TIMEOUT_SECONDS", 600)

    # --- AI providers ----------------------------------------------------------
    # transcription: none | faster_whisper | openai
    TRANSCRIPTION_PROVIDER = os.environ.get("TRANSCRIPTION_PROVIDER", "none").lower()
    WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "small")
    WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
    WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
    OPENAI_TRANSCRIPTION_MODEL = os.environ.get("OPENAI_TRANSCRIPTION_MODEL", "whisper-1")
    # LLM (summaries, metadata, RAG answers) and translation: none | openai
    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "none").lower()
    TRANSLATION_PROVIDER = os.environ.get("TRANSLATION_PROVIDER", "none").lower()
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or None
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or None
    OPENAI_CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    AI_TIMEOUT_SECONDS = _int("AI_TIMEOUT_SECONDS", 90)
    AI_MAX_RETRIES = _int("AI_MAX_RETRIES", 2)
    # RapidAPI YouTube transcript provider. Keep the key server-side.
    YOUTUBE_TRANSCRIPT_API_URL = os.environ.get(
        "YOUTUBE_TRANSCRIPT_API_URL",
        "https://youtube-transcript3.p.rapidapi.com/api/transcript",
    )
    YOUTUBE_TRANSCRIPT_API_HOST = os.environ.get(
        "YOUTUBE_TRANSCRIPT_API_HOST",
        "youtube-transcript3.p.rapidapi.com",
    )
    RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY") or None
    # embeddings: sentence_transformers | test_hash | none
    EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "sentence_transformers").lower()
    EMBEDDING_MODEL = os.environ.get(
        "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    VECTOR_DIR = os.environ.get("VECTOR_DIR") or str(BASE_DIR / "instance" / "chroma")

    ITEMS_PER_PAGE = 9


class DevelopmentConfig(Config):
    APP_ENV = "development"


class ProductionConfig(Config):
    APP_ENV = "production"
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"


class TestingConfig(Config):
    APP_ENV = "testing"
    TESTING = True
    SECRET_KEY = "test-secret-key-not-for-production"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    PROCESSING_SYNC = True
    TRANSCRIPTION_PROVIDER = "none"
    LLM_PROVIDER = "none"
    TRANSLATION_PROVIDER = "none"
    OPENAI_API_KEY = None
    EMBEDDING_PROVIDER = "test_hash"


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
