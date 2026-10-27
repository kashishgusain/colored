import tempfile
from pathlib import Path

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Length

from ..extensions import csrf, db, limiter
from ..models import Category, ContactMessage, KnowledgeRecord, Role, Status, User
from ..services import media, steps, transcription, youtube_transcript
from ..services.errors import ServiceError, UploadError
from ..utils import contributor_required
from . import bp


class ContactForm(FlaskForm):
    name = StringField("Your name", validators=[DataRequired(), Length(2, 100)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=254)])
    subject = StringField("Subject", validators=[DataRequired(), Length(3, 150)])
    message = TextAreaField("Message", validators=[DataRequired(), Length(10, 3000)])


@bp.route("/")
def index():
    pub = KnowledgeRecord.public_query()
    total = pub.count()
    featured = pub.order_by(KnowledgeRecord.approved_at.desc().nullslast()).limit(3).all()
    counts = dict(db.session.query(KnowledgeRecord.category_id, func.count(KnowledgeRecord.id))
                  .filter(KnowledgeRecord.id.in_(pub.with_entities(KnowledgeRecord.id)))
                  .group_by(KnowledgeRecord.category_id).all())
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    stats = {
        "records": total,
        "recordings": pub.filter(KnowledgeRecord.content_type.in_(("audio", "video"))).count(),
        "contributors": db.session.query(func.count(func.distinct(KnowledgeRecord.owner_id)))
                          .filter(KnowledgeRecord.id.in_(pub.with_entities(KnowledgeRecord.id))).scalar() or 0,
        "districts": db.session.query(func.count(func.distinct(KnowledgeRecord.district)))
                       .filter(KnowledgeRecord.id.in_(pub.with_entities(KnowledgeRecord.id)),
                               KnowledgeRecord.district.isnot(None)).scalar() or 0,
    }
    return render_template("index.html", featured=featured, categories=categories, counts=counts, stats=stats)


@bp.route("/dashboard")
@login_required
def dashboard():
    mine = (KnowledgeRecord.query.filter_by(owner_id=current_user.id)
            .order_by(KnowledgeRecord.updated_at.desc()).all())
    by_status = {}
    for r in mine:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    pending_reviews = (KnowledgeRecord.query.filter_by(status=Status.PENDING).count()
                       if current_user.role in Role.CAN_REVIEW else None)
    return render_template("dashboard.html", records=mine, by_status=by_status, pending_reviews=pending_reviews)


@bp.route("/about")
def about():
    return render_template("about.html")


@bp.route("/privacy")
def privacy():
    return render_template("privacy.html")


@bp.route("/contact", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def contact():
    form = ContactForm()
    if current_user.is_authenticated and not form.is_submitted():
        form.name.data, form.email.data = current_user.display_name, current_user.email
    if form.validate_on_submit():
        db.session.add(ContactMessage(name=form.name.data.strip(), email=form.email.data.strip().lower(),
                                      subject=form.subject.data.strip(), message=form.message.data.strip()))
        db.session.commit()
        flash("Thank you. Your message has been received by the LOKVAANI team.", "success")
        return redirect(url_for("main.contact"))
    return render_template("contact.html", form=form)


@bp.route("/api/transcript", methods=["POST"])
@csrf.exempt
@contributor_required
@limiter.limit("10 per hour")
def api_transcript():
    """Transcribe an uploaded video and return source-grounded procedural steps."""
    upload = request.files.get("video")
    language = (request.form.get("language") or "hindi").strip().lower()
    if language not in {"hindi", "english", "garhwali", "kumaoni", "jaunsari", "other"}:
        return jsonify({"error": "Unsupported language."}), 400

    try:
        _kind, ext, _ = media.validate_upload(upload, ("video",))
    except UploadError as exc:
        return jsonify({"error": str(exc), "code": "INVALID_VIDEO"}), 400

    temp_video = None
    temp_audio = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as fh:
            temp_video = Path(fh.name)
            upload.stream.seek(0)
            for chunk in iter(lambda: upload.stream.read(1024 * 1024), b""):
                fh.write(chunk)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
            temp_audio = Path(fh.name)
        audio = media.extract_audio(temp_video, temp_audio)
        result = transcription.transcribe(audio, language)
        extracted = steps.from_transcript(result["text"])
        return jsonify({
            "transcript": result["text"],
            "language": result.get("language"),
            "provider": result["provider"],
            "model": result.get("model"),
            "steps": extracted["steps"],
            "steps_mode": extracted["mode"],
            "warning": transcription.dialect_warning(language),
        })
    except (ServiceError, UploadError) as exc:
        return jsonify({"error": str(exc), "code": exc.code}), 422
    finally:
        for path in (temp_video, temp_audio):
            if path:
                path.unlink(missing_ok=True)


@bp.route("/api/youtube-transcript", methods=["POST"])
@csrf.exempt
@contributor_required
@limiter.limit("10 per hour")
def api_youtube_transcript():
    """Extract a YouTube transcript and source-grounded procedural steps."""
    payload = request.get_json(silent=True) or {}
    try:
        result = youtube_transcript.extract(payload.get("url", ""))
        return jsonify(result)
    except ServiceError as exc:
        return jsonify({"error": str(exc), "code": exc.code}), 422
