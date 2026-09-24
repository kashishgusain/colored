import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    DEBUG = os.environ.get("FLASK_DEBUG", "true").lower() == "true"

    DATABASE_PATH = os.path.join(BASE_DIR, os.environ.get("DATABASE_PATH", "lokvaani.db"))

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    ALLOWED_EXTENSIONS = {"mp4", "mov", "webm", "mp3", "wav", "m4a"}
    MAX_CONTENT_LENGTH = 300 * 1024 * 1024  # 300 MB, generous for a short demo clip

    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
    GROQ_WHISPER_MODEL = os.environ.get("GROQ_WHISPER_MODEL", "whisper-large-v3")
    GROQ_LLM_MODEL = os.environ.get("GROQ_LLM_MODEL", "llama-3.1-70b-versatile")

    # If no API key is configured, the AI pipeline runs in demo mode:
    # it still exercises every stage of the pipeline, but labels its
    # output clearly as demo/fallback rather than pretending it is live.
    AI_DEMO_MODE = GROQ_API_KEY == ""

    EMBEDDING_DIM = 256
