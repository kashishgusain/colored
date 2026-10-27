"""Background processing pipeline: validate -> extract audio -> transcribe -> translate -> analyse.

Each stage records progress on the ProcessingJob. Nothing is invented: when a provider is missing the
job fails (or skips the optional stage) with an explicit, actionable message.
"""
import tempfile
import threading
import time
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import current_app

from ..extensions import db
from ..models import (Category, JobStatus, KnowledgeRecord, ProcessingJob, Status, Transcript, Translation, audit,
                      utcnow)
from . import media, summarization, translation, transcription
from .errors import NotConfigured, ServiceError

_executor = None
_executor_lock = threading.Lock()


def _get_executor(app):
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=app.config["PROCESSING_WORKERS"],
                                           thread_name_prefix="lokvaani-job")
        return _executor


def enqueue(record: KnowledgeRecord, actor=None) -> ProcessingJob:
    """Create a job, move the record to Processing and start the work."""
    record.transition(Status.PROCESSING)
    job = ProcessingJob(record_id=record.id, status=JobStatus.QUEUED, stage="queued", progress=0)
    db.session.add(job)
    audit("processing.queued", actor, "record", record.id)
    db.session.commit()
    app = current_app._get_current_object()
    if app.config["PROCESSING_SYNC"]:
        run_job(app, job.id)
        db.session.refresh(job)
    else:
        _get_executor(app).submit(run_job, app, job.id)
    return job


def _set(job, stage, progress):
    job.stage, job.progress = stage, progress
    db.session.commit()


def run_job(app, job_id: int) -> None:
    with app.app_context():
        job = db.session.get(ProcessingJob, job_id)
        if not job:
            return
        record = db.session.get(KnowledgeRecord, job.record_id)
        job.status, job.started_at, job.attempts = JobStatus.RUNNING, utcnow(), job.attempts + 1
        db.session.commit()
        warnings: list[str] = []
        tmpdir = tempfile.mkdtemp(prefix="lokvaani-")
        try:
            _process(record, job, Path(tmpdir), warnings)
            job.status, job.stage, job.progress = JobStatus.SUCCEEDED, "done", 100
            job.error_code = job.error_message = None
        except ServiceError as exc:
            job.status, job.error_code, job.error_message = JobStatus.FAILED, exc.code, str(exc)
        except Exception as exc:  # unexpected: log details, show a safe message
            current_app.logger.exception("Processing job %s crashed", job.id)
            job.status, job.error_code = JobStatus.FAILED, "UNEXPECTED_ERROR"
            job.error_message = f"Unexpected error ({type(exc).__name__}). An administrator can see the server log."
        finally:
            job.finished_at = utcnow()
            job.warnings = "\n".join(warnings) or None
            if record.status == Status.PROCESSING:
                record.transition(Status.DRAFT)  # contributor reviews output (or fixes the error)
            audit(f"processing.{job.status}", None, "record", record.id, job.error_code)
            db.session.commit()
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


def _with_retries(fn, attempts: int):
    last = None
    for i in range(max(1, attempts)):
        try:
            return fn()
        except ServiceError as exc:
            last = exc
            if not exc.retryable or i == attempts - 1:
                raise
            time.sleep(min(2 ** i, 8))
    raise last  # pragma: no cover


def _analyze_metadata(record, text: str, retries: int, warnings: list[str]) -> None:
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    try:
        analysis = _with_retries(
            lambda: summarization.analyze(
                text, record.title, record.category.name, record.language,
                [(category.slug, category.name) for category in categories],
            ),
            retries,
        )
        record.ai_suggested_tags = ",".join(analysis["tags"])[:400]
        metadata = record.ai_metadata
        metadata.update(analysis["metadata"])
        metadata["suggested_summary"] = analysis["summary"]
        metadata["suggested_category"] = analysis["suggested_category"]
        record.ai_metadata_json = json.dumps(metadata, ensure_ascii=False)
    except NotConfigured as exc:
        warnings.append(f"Summary and metadata skipped: {exc}")
    except ServiceError as exc:
        warnings.append(f"Summary and metadata failed ({exc.code}).")


def _process(record, job, tmp: Path, warnings: list[str]):
    cfg = current_app.config
    retries = cfg["AI_MAX_RETRIES"] + 1
    if record.content_type == "text":
        _set(job, "analysing", 15)
        source = "\n\n".join(part.strip() for part in (record.description, record.body_text) if part and part.strip())
        _analyze_metadata(record, source, retries, warnings)
        db.session.commit()
        return

    asset = record.primary_media
    if asset is None:
        raise ServiceError("This record has no audio or video file to process.", code="NO_MEDIA")
    _set(job, "validating", 5)
    src = media.asset_path(asset)
    if not src.exists():
        raise ServiceError("The stored media file is missing from disk.", code="MEDIA_MISSING")

    audio = src
    if asset.kind == "video":
        _set(job, "extracting_audio", 15)
        audio = _with_retries(lambda: media.extract_audio(src, tmp / "audio.wav"), retries)

    _set(job, "transcribing", 35)
    existing = record.transcript
    if existing and (existing.edited_text or "").strip():
        warnings.append("Kept your corrected transcript; speech-to-text was not re-run.")
        text = existing.edited_text
    else:
        result = _with_retries(lambda: transcription.transcribe(audio, record.language), retries)
        text = result["text"]
        if existing is None:
            existing = Transcript(record_id=record.id)
            db.session.add(existing)
        existing.original_text = text  # preserved exactly as produced
        existing.edited_text = None
        existing.source, existing.model_name = result["provider"], result.get("model")
        existing.detected_language = result.get("language")
        warn = transcription.dialect_warning(record.language)
        if warn:
            warnings.append(warn)
        db.session.commit()

    _set(job, "translating", 60)
    for target in ("hi", "en"):
        src_lang = record.language
        if (src_lang == "hindi" and target == "hi") or (src_lang == "english" and target == "en"):
            continue
        try:
            translated = _with_retries(lambda: translation.translate(text, src_lang, target), retries)
        except NotConfigured as exc:
            warnings.append(f"Translation to {'Hindi' if target == 'hi' else 'English'} skipped: {exc}")
            break
        except ServiceError as exc:
            warnings.append(f"Translation to {'Hindi' if target == 'hi' else 'English'} failed ({exc.code}).")
            continue
        row = record.translation_for(target)
        if row is None:
            row = Translation(record_id=record.id, target_language=target)
            db.session.add(row)
        if not row.is_human_edited:
            row.text = row.machine_text = translated
            row.provider = cfg["TRANSLATION_PROVIDER"]
    db.session.commit()

    _set(job, "analysing", 85)
    source = "\n\n".join(part.strip() for part in (record.description, text) if part and part.strip())
    _analyze_metadata(record, source, retries, warnings)
    db.session.commit()
