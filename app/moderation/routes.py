from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user

from ..extensions import db
from ..models import InvalidTransition, KnowledgeRecord, Review, Role, Status, audit, normalise_tags, utcnow
from ..services import records as record_service, retrieval, transcription
from ..utils import steward_required
from . import bp
from .forms import DecisionForm, StewardEditForm


def _record_or_404(record_id) -> KnowledgeRecord:
    record = db.session.get(KnowledgeRecord, record_id)
    if record is None:
        abort(404)
    return record


@bp.route("/")
@steward_required
def dashboard():
    pending = (KnowledgeRecord.query.filter_by(status=Status.PENDING)
               .order_by(KnowledgeRecord.submitted_at.asc()).all())
    revision = (KnowledgeRecord.query.filter_by(status=Status.NEEDS_REVISION)
                .order_by(KnowledgeRecord.updated_at.desc()).limit(20).all())
    recent = Review.query.order_by(Review.id.desc()).limit(15).all()
    return render_template("moderation/dashboard.html", pending=pending, revision=revision, recent=recent)


@bp.route("/<int:record_id>")
@steward_required
def review(record_id):
    record = _record_or_404(record_id)
    form = StewardEditForm(obj=record)
    form.transcript_text.data = record.transcript_text
    hi, en = record.translation_for("hi"), record.translation_for("en")
    form.translation_hi.data, form.translation_en.data = (hi.text if hi else ""), (en.text if en else "")
    return render_template("moderation/review.html", record=record, form=form, decision_form=DecisionForm(),
                           own=record.owner_id == current_user.id,
                           dialect_warning=transcription.dialect_warning(record.language) if record.primary_media else None)


@bp.route("/<int:record_id>/edit", methods=["POST"])
@steward_required
def edit(record_id):
    record = _record_or_404(record_id)
    if record.status in (Status.PROCESSING, Status.WITHDRAWN):
        flash("This record cannot be edited right now.", "warning")
        return redirect(url_for("moderation.review", record_id=record.id))
    form = StewardEditForm()
    if not form.validate_on_submit():
        flash("Some fields are invalid: " + "; ".join(f"{k}: {v[0]}" for k, v in form.errors.items()), "danger")
        return redirect(url_for("moderation.review", record_id=record.id))
    record.title, record.description = form.title.data, form.description.data.strip()
    record.category_id, record.tags = form.category_id.data, normalise_tags(form.tags.data)
    record.summary = (form.summary.data or "").strip() or None
    if record.content_type == "text":
        record.body_text = (form.body_text.data or "").strip() or None
    else:
        record_service.set_transcript_text(record, form.transcript_text.data, current_user)
        record_service.set_translation(record, "hi", form.translation_hi.data)
        record_service.set_translation(record, "en", form.translation_en.data)
    audit("record.steward_edited", current_user, "record", record.id)
    outcome = retrieval.sync_record(record)  # approved records are re-indexed with the corrected text
    db.session.commit()
    flash("Changes saved." + (" The search index was updated." if outcome.startswith("indexed") else ""), "success")
    return redirect(url_for("moderation.review", record_id=record.id))


@bp.route("/<int:record_id>/decision", methods=["POST"])
@steward_required
def decide(record_id):
    record = _record_or_404(record_id)
    form = DecisionForm()
    if not form.validate_on_submit():
        abort(400)
    action = form.decision.data
    comment = (form.comment.data or "").strip()

    if record.owner_id == current_user.id and current_user.role != Role.ADMIN:
        flash("You cannot review your own submission. Another steward must do it.", "danger")
        return redirect(url_for("moderation.review", record_id=record.id))

    if action == "comment":
        if not comment:
            flash("Write a note first.", "warning")
        else:
            db.session.add(Review(record_id=record.id, reviewer_id=current_user.id, decision="comment",
                                  from_status=record.status, to_status=record.status, comment=comment))
            audit("review.comment", current_user, "record", record.id)
            db.session.commit()
            flash("Note added to the review log.", "success")
        return redirect(url_for("moderation.review", record_id=record.id))

    target = {"approve": Status.APPROVED, "revise": Status.NEEDS_REVISION, "reject": Status.REJECTED}.get(action)
    if target is None:
        abort(400)
    if action in ("revise", "reject") and not comment:
        flash("Please explain your decision so the contributor knows what to do next.", "danger")
        return redirect(url_for("moderation.review", record_id=record.id))
    if action == "reject" and record.status == Status.APPROVED:
        flash("Approved records cannot be rejected. Request corrections instead, which removes them from public view.", "danger")
        return redirect(url_for("moderation.review", record_id=record.id))
    if action == "approve":
        if not record.consent_given:
            flash("This contribution has no recorded consent and cannot be approved.", "danger")
            return redirect(url_for("moderation.review", record_id=record.id))
        if not record.searchable_text().strip() or (record.content_type != "text" and not record.transcript_text.strip()):
            flash("Add or correct the transcript before approving.", "danger")
            return redirect(url_for("moderation.review", record_id=record.id))

    previous = record.status
    try:
        record.transition(target)
    except InvalidTransition as exc:
        flash(str(exc), "danger")
        return redirect(url_for("moderation.review", record_id=record.id))
    record.steward_note = comment or None
    if target == Status.APPROVED:
        record.approved_at, record.verified_by_id = utcnow(), current_user.id
    elif target in (Status.REJECTED, Status.NEEDS_REVISION):
        record.approved_at = None
    db.session.add(Review(record_id=record.id, reviewer_id=current_user.id, decision=target, from_status=previous,
                          to_status=target, comment=comment or None))
    detail = "self-review by admin" if record.owner_id == current_user.id else None
    audit(f"review.{target}", current_user, "record", record.id, detail)
    outcome = retrieval.sync_record(record)
    db.session.commit()

    if target == Status.APPROVED and not record.is_public:
        flash("Approved as a PRIVATE record: the contributor chose not to publish it, so it stays out of public search.", "info")
    elif target == Status.APPROVED and outcome.startswith("index_failed"):
        flash("Approved and public. The semantic index could not be updated (keyword search still finds it). "
              "Run `flask reindex` once the embedding model is available.", "warning")
    else:
        flash(f"Decision saved: {Status.LABELS[target]}.", "success")
    return redirect(url_for("moderation.dashboard"))
