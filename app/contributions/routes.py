import json

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db, limiter
from ..models import Category, InvalidTransition, JobStatus, KnowledgeRecord, Status, audit, normalise_tags, utcnow
from ..services import media, pipeline, records as record_service, retrieval, transcription, translation
from ..services.errors import UploadError
from ..utils import contributor_required
from . import bp
from .forms import EditRecordForm, NewRecordForm


def _own_record(record_id) -> KnowledgeRecord:
    record = db.session.get(KnowledgeRecord, record_id)
    if record is None or record.owner_id != current_user.id:
        abort(404)
    return record


@bp.route("/new", methods=["GET", "POST"])
@contributor_required
@limiter.limit("30 per hour", methods=["POST"])
def new():
    form = NewRecordForm()
    if not form.category_id.choices:
        flash("No cultural categories exist yet. Ask an administrator to run `flask seed-categories`.", "warning")
    if request.method == "GET" and request.args.get("type") in ("text", "media"):
        form.submission_type.data = request.args["type"]
    if form.validate_on_submit():
        try:
            kind = ext = None
            is_media = form.submission_type.data == "media"
            if is_media:
                kind, ext, _ = media.validate_upload(form.media_file.data, ("audio", "video"))
            photo_checks = [(f, *media.validate_upload(f, ("photo",))) for f in (form.photos.data or []) if f and f.filename]
            if len(photo_checks) > 6:
                raise UploadError("Please attach at most 6 photographs.")
            doc_check = None
            if form.document.data and form.document.data.filename:
                doc_check = (form.document.data, *media.validate_upload(form.document.data, ("document",)))
        except UploadError as exc:
            flash(str(exc), "danger")
            return render_template("contributions/new.html", form=form), 400

        record = KnowledgeRecord(
            owner_id=current_user.id, category_id=form.category_id.data, title=form.title.data,
            description=form.description.data.strip(), content_type=(kind or "text"),
            body_text=(form.body_text.data or "").strip() or None, language=form.language.data,
            district=form.district.data or None, village=(form.village.data or "").strip() or None,
            tags=normalise_tags(form.tags.data), attribution=form.attribution.data,
            is_public=form.is_public.data == "1", consent_given=True, consent_at=utcnow(), status=Status.DRAFT)
        try:
            db.session.add(record)
            db.session.flush()
            if is_media:
                asset = media.save_upload(form.media_file.data, record.id, kind, ext)
                db.session.add(asset)
            for f, k, e, _s in photo_checks:
                db.session.add(media.save_upload(f, record.id, k, e))
            if doc_check:
                f, k, e, _s = doc_check
                db.session.add(media.save_upload(f, record.id, k, e))
            audit("record.created", current_user, "record", record.id, record.content_type)
            db.session.commit()
        except (SQLAlchemyError, OSError, UploadError) as exc:
            db.session.rollback()
            media.delete_record_files(record.id if record.id else 0)
            flash("Your contribution could not be saved. Please try again.", "danger")
            return render_template("contributions/new.html", form=form), 500

        pipeline.enqueue(record, current_user)
        if is_media:
            flash("Recording uploaded. LOKVAANI is processing it now.", "success")
        else:
            flash("Draft saved. LOKVAANI is preparing summary and tag suggestions for your review.", "success")
        return redirect(url_for("contributions.manage", record_id=record.id))
    return render_template("contributions/new.html", form=form)


@bp.route("/<int:record_id>")
@contributor_required
def manage(record_id):
    record = _own_record(record_id)
    job = record.jobs[0] if record.jobs else None
    return render_template("contributions/manage.html", record=record, job=job,
                           dialect_warning=transcription.dialect_warning(record.language) if record.primary_media else None,
                           translation_on=translation.available())


@bp.route("/<int:record_id>/status.json")
@contributor_required
def status_json(record_id):
    record = _own_record(record_id)
    job = record.jobs[0] if record.jobs else None
    return jsonify({"status": record.status, "status_label": record.status_label,
                    "job": None if not job else {"status": job.status, "stage": job.stage, "progress": job.progress,
                                                 "error_code": job.error_code, "error": job.error_message}})


@bp.route("/<int:record_id>/edit", methods=["GET", "POST"])
@contributor_required
def edit(record_id):
    record = _own_record(record_id)
    if record.status in (Status.PROCESSING, Status.REJECTED, Status.WITHDRAWN):
        flash(f"A record that is {record.status_label.lower()} cannot be edited.", "warning")
        return redirect(url_for("contributions.manage", record_id=record.id))
    form = EditRecordForm(obj=record)
    if request.method == "GET":
        form.is_public.data = "1" if record.is_public else "0"
        form.transcript_text.data = record.transcript_text
        hi, en = record.translation_for("hi"), record.translation_for("en")
        form.translation_hi.data, form.translation_en.data = (hi.text if hi else ""), (en.text if en else "")
    if form.validate_on_submit():
        was_approved = record.status == Status.APPROVED
        record.title, record.description = form.title.data, form.description.data.strip()
        record.category_id, record.language = form.category_id.data, form.language.data
        record.district, record.village = form.district.data or None, (form.village.data or "").strip() or None
        record.tags, record.attribution = normalise_tags(form.tags.data), form.attribution.data
        record.is_public = form.is_public.data == "1"
        record.summary = (form.summary.data or "").strip() or None
        record.body_text = (form.body_text.data or "").strip() or None
        if record.content_type == "text" and len(record.body_text or "") < 50:
            db.session.rollback()
            flash("A written record needs at least 50 characters of text.", "danger")
            return render_template("contributions/edit.html", record=record, form=form), 400
        if record.content_type != "text":
            record_service.set_transcript_text(record, form.transcript_text.data, current_user)
            record_service.set_translation(record, "hi", form.translation_hi.data)
            record_service.set_translation(record, "en", form.translation_en.data)
        if was_approved:  # an edited approved record must be re-verified and leaves the public index
            record.transition(Status.PENDING)
            record.approved_at = None
            record.submitted_at = utcnow()
            flash("Your changes were saved. Because this record was already approved, it is back in review "
                  "and hidden from public search until a steward approves it again.", "info")
        else:
            flash("Changes saved.", "success")
        audit("record.edited", current_user, "record", record.id)
        retrieval.sync_record(record)
        db.session.commit()
        return redirect(url_for("contributions.manage", record_id=record.id))
    return render_template("contributions/edit.html", record=record, form=form)


@bp.route("/<int:record_id>/submit", methods=["POST"])
@contributor_required
def submit(record_id):
    record = _own_record(record_id)
    if record.status not in (Status.DRAFT, Status.NEEDS_REVISION):
        flash("This record cannot be submitted from its current status.", "warning")
    elif not record.consent_given:
        flash("Consent is required before submission.", "danger")
    elif record.content_type == "text" and len(record.body_text or "") < 50:
        flash("Add the written text before submitting.", "danger")
    elif record.content_type != "text" and not record.transcript_text.strip():
        flash("This recording has no transcript yet. Retry processing or type the transcript, then submit.", "danger")
    else:
        record.transition(Status.PENDING)
        record.submitted_at = utcnow()
        audit("record.submitted", current_user, "record", record.id)
        db.session.commit()
        flash("Submitted. A Community Steward will review it. Nothing is published until then.", "success")
    return redirect(url_for("contributions.manage", record_id=record.id))


@bp.route("/<int:record_id>/retry", methods=["POST"])
@contributor_required
@limiter.limit("10 per hour")
def retry(record_id):
    record = _own_record(record_id)
    if (record.content_type != "text" and record.primary_media is None) or record.status not in (Status.DRAFT, Status.NEEDS_REVISION):
        flash("Processing can only be retried for a draft contribution.", "warning")
    elif record.jobs and record.jobs[0].status in (JobStatus.QUEUED, JobStatus.RUNNING):
        flash("Processing is already running.", "info")
    else:
        pipeline.enqueue(record, current_user)
        flash("Processing restarted.", "info")
    return redirect(url_for("contributions.manage", record_id=record.id))


@bp.route("/<int:record_id>/withdraw", methods=["POST"])
@contributor_required
def withdraw(record_id):
    """Take a record out of the public archive and the AI index. The record stays visible to its owner."""
    record = _own_record(record_id)
    try:
        record.transition(Status.WITHDRAWN)
    except InvalidTransition:
        flash("Only records in review or approved records can be withdrawn.", "warning")
        return redirect(url_for("contributions.manage", record_id=record.id))
    record.is_public, record.withdrawn_at = False, utcnow()
    audit("record.withdrawn", current_user, "record", record.id)
    retrieval.sync_record(record)
    db.session.commit()
    flash("Your record was withdrawn. It is no longer public or searchable by the assistant.", "success")
    return redirect(url_for("contributions.manage", record_id=record.id))


@bp.route("/<int:record_id>/delete", methods=["POST"])
@contributor_required
def delete(record_id):
    """Permanent deletion: database rows, stored files and vectors are all removed."""
    record = _own_record(record_id)
    if record.status == Status.PROCESSING:
        flash("Wait for processing to finish before deleting.", "warning")
        return redirect(url_for("contributions.manage", record_id=record.id))
    rid = record.id
    retrieval.remove_record(rid)
    retrieval.redact_chats_for_record(rid)
    media.delete_record_files(rid)
    audit("record.deleted", current_user, "record", rid, f"status={record.status}")
    db.session.delete(record)
    db.session.commit()
    flash("The record and its files were permanently deleted.", "success")
    return redirect(url_for("main.dashboard"))
