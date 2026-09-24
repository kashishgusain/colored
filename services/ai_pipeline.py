"""
AI pipeline for LOKVAANI AI.

Every function here either makes a real call to Groq's free API, or -
if no GROQ_API_KEY is configured, or the call fails - returns a result
that is CLEARLY flagged as demo/fallback (`is_demo=True`). Callers must
surface that flag to the user. We never silently dress up a failure or
an absent API key as a real AI result.
"""
import hashlib
import json
import math
import re
import subprocess

VIDEO_EXTENSIONS = {"mp4", "mov", "webm"}

EXTRACTION_SYSTEM_PROMPT = """You are a careful documentation assistant for LOKVAANI AI, a \
platform that preserves traditional/oral knowledge from Uttarakhand, India. You will be given \
a transcript of a knowledge holder describing a traditional practice, in their own words \
(possibly in Hindi, Garhwali, Kumaoni or English).

Translate the transcript into clear English, then extract structured knowledge from it.
Only use information that is actually present in the transcript. Do not invent facts,
statistics, dates, or claims that are not supported by the transcript.

Respond ONLY with a single JSON object with exactly these fields:
{
  "translation_en": "full English translation of the transcript",
  "title": "short descriptive title for this practice",
  "category_guess": "one of: Traditional Agriculture, Seed Preservation, Food Heritage, \
Handicrafts, Folk Culture, Traditional Architecture, Water & Environment, Oral History, \
Traditional Tools, Local Plant Knowledge, Ayurveda-related Traditional Knowledge, \
Festivals & Traditions, Vanishing Skills, Local Products",
  "materials": ["list", "of", "materials mentioned"],
  "tools": ["list", "of", "tools mentioned"],
  "steps": ["ordered", "list", "of", "steps described"],
  "cultural_significance": "1-2 sentences, only if the transcript actually discusses this",
  "historical_context": "1-2 sentences, only if the transcript actually discusses this",
  "summary": "2-3 sentence plain-language summary",
  "keywords": ["5-8", "search", "keywords"]
}
If the transcript does not contain enough information for a field, use an empty string or
empty list for that field rather than inventing content."""


class AIPipelineError(Exception):
    pass


def _get_groq_client(app_config):
    if app_config["AI_DEMO_MODE"]:
        return None
    try:
        from groq import Groq
    except ImportError:
        return None
    return Groq(api_key=app_config["GROQ_API_KEY"])


def extract_audio_if_needed(source_path, dest_path):
    """For video files, pull out a mono 16kHz WAV track with ffmpeg.
    Audio-only uploads are returned unchanged. Requires ffmpeg on PATH."""
    ext = source_path.rsplit(".", 1)[-1].lower()
    if ext not in VIDEO_EXTENSIONS:
        return source_path
    cmd = ["ffmpeg", "-y", "-i", source_path, "-ar", "16000", "-ac", "1", "-vn", dest_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise AIPipelineError(
            "Could not extract audio from this video (is ffmpeg installed?). "
            "Try uploading an audio file (mp3/wav/m4a) instead."
        )
    return dest_path


def transcribe_audio(audio_path, app_config):
    """Returns {transcript, language, is_demo}."""
    client = _get_groq_client(app_config)
    if client is None:
        return {
            "transcript": (
                "[DEMO MODE - no GROQ_API_KEY configured] This is placeholder transcript "
                "text standing in for real Whisper transcription. Set GROQ_API_KEY in your "
                ".env file to transcribe real audio."
            ),
            "language": "unknown",
            "is_demo": True,
        }
    try:
        with open(audio_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                file=(audio_path.split("/")[-1], f.read()),
                model=app_config["GROQ_WHISPER_MODEL"],
                response_format="verbose_json",
            )
        transcript = getattr(resp, "text", "") or ""
        language = getattr(resp, "language", "unknown") or "unknown"
        if not transcript.strip():
            raise AIPipelineError("Transcription returned empty text.")
        return {"transcript": transcript, "language": language, "is_demo": False}
    except Exception as exc:  # noqa: BLE001 - surface any provider error the same way
        raise AIPipelineError(f"Transcription failed: {exc}") from exc


def translate_and_extract(transcript, app_config):
    """Returns a dict matching EXTRACTION_SYSTEM_PROMPT's JSON shape, plus is_demo."""
    client = _get_groq_client(app_config)
    if client is None:
        return {
            "translation_en": transcript,
            "title": "Untitled knowledge record (demo mode)",
            "category_guess": "",
            "materials": [],
            "tools": [],
            "steps": [],
            "cultural_significance": "",
            "historical_context": "",
            "summary": "AI extraction did not run because no GROQ_API_KEY is configured. "
                       "This record needs to be filled in manually before review.",
            "keywords": [],
            "is_demo": True,
        }
    try:
        resp = client.chat.completions.create(
            model=app_config["GROQ_LLM_MODEL"],
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(resp.choices[0].message.content)
        data["is_demo"] = False
        return data
    except Exception as exc:  # noqa: BLE001
        raise AIPipelineError(f"Knowledge extraction failed: {exc}") from exc


def generate_rag_answer(question, context_chunks, app_config):
    """context_chunks: list of dicts with knowledge_id, title, summary, status.
    Returns {answer, is_demo}."""
    client = _get_groq_client(app_config)
    if not context_chunks:
        return {
            "answer": "LOKVAANI does not currently have enough verified information to "
                      "answer this confidently.",
            "is_demo": False,
        }
    if client is None:
        titles = "; ".join(c["title"] for c in context_chunks[:3])
        return {
            "answer": f"[DEMO MODE] The closest matching records are: {titles}. "
                      "Configure GROQ_API_KEY to generate a real grounded answer.",
            "is_demo": True,
        }
    context_text = "\n\n".join(
        f"Knowledge ID: {c['knowledge_id']}\nTitle: {c['title']}\nStatus: {c['status']}\n"
        f"Summary: {c['summary']}"
        for c in context_chunks
    )
    system = (
        "You are Ask LOKVAANI AI. Answer the user's question using ONLY the knowledge "
        "records provided below. Cite the Knowledge ID(s) you used. If the records don't "
        "contain enough information, say so plainly instead of guessing. Never invent "
        "traditional knowledge that isn't in the provided records."
    )
    try:
        resp = client.chat.completions.create(
            model=app_config["GROQ_LLM_MODEL"],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Records:\n{context_text}\n\nQuestion: {question}"},
            ],
            temperature=0.2,
        )
        return {"answer": resp.choices[0].message.content, "is_demo": False}
    except Exception as exc:  # noqa: BLE001
        raise AIPipelineError(f"Answer generation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Local embeddings - a deterministic hashing-trick bag-of-words vectorizer.
# Zero external downloads or API calls, so semantic search and RAG retrieval
# work even with no internet access or GROQ key. Swap in sentence-transformers
# later for stronger quality if you have time/bandwidth - embed_text() is the
# only function you'd need to change.
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-zA-Z\u0900-\u097F]+")


def embed_text(text, dim=256):
    vec = [0.0] * dim
    tokens = _TOKEN_RE.findall((text or "").lower())
    if not tokens:
        return vec
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(a, b):
    return sum(x * y for x, y in zip(a, b))
