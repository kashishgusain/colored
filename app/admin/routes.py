import re

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import StringField
from wtforms.validators import DataRequired, Length

from ..extensions import db
from ..models import (AuditLog, Category, ContactMessage, JobStatus, KnowledgeRecord, ProcessingJob, Review, Role,
                      Status, User, audit)
from ..services import llm, media, retrieval, transcription
from ..utils import admin_required
from . import bp


class CategoryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(2, 80)])
    description = StringField("Description", validators=[Length(max=300)])


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "category"


@bp.route("/")
@admin_required
def dashboard():
    by_status = dict(db.session.query(KnowledgeRecord.status, func.count()).group_by(KnowledgeRecord.status).all())
    stats = {
        "users": User.query.count(),
        "users_by_role": dict(db.session.query(User.role, func.count()).group_by(User.role).all()),
        "records": KnowledgeRecord.query.count(),
        "approved": by_status.get(Status.APPROVED, 0),
        "pending": by_status.get(Status.PENDING, 0),
        "rejected": by_status.get(Status.REJECTED, 0),
        "needs_revision": by_status.get(Status.NEEDS_REVISION, 0),
        "public": KnowledgeRecord.public_query().count(),
        "failed_jobs": ProcessingJob.query.filter_by(status=JobStatus.FAILED).count(),
        "messages": ContactMessage.query.filter_by(is_resolved=False).count(),
    }
    recent = AuditLog.query.order_by(AuditLog.id.desc()).limit(12).all()
    return render_template("admin/dashboard.html", stats=stats, recent=recent)


@bp.route("/users")
@admin_required
def users():
    q = (request.args.get("q") or "").strip()
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter(User.username.ilike(like) | User.email.ilike(like) | User.display_name.ilike(like))
    if request.args.get("role") in Role.ALL:
        query = query.filter_by(role=request.args["role"])
    page = max(request.args.get("page", 1, type=int), 1)
    pag = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("admin/users.html", pag=pag, q=q, role_filter=request.args.get("role", ""))


@bp.route("/users/<int:user_id>/role", methods=["POST"])
@admin_required
def set_role(user_id):
    user = db.session.get(User, user_id) or abort(404)
    role = request.form.get("role")
    if role not in Role.ALL:
        abort(400)
    if user.id == current_user.id:
        flash("You cannot change your own role.", "danger")
    else:
        old, user.role = user.role, role
        audit("admin.role_changed", current_user, "user", user.id, f"{old} -> {role}")
        db.session.commit()
        flash(f"{user.display_name} is now {Role.LABELS[role]}.", "success")
    return redirect(request.referrer or url_for("admin.users"))


@bp.route("/users/<int:user_id>/active", methods=["POST"])
@admin_required
def set_active(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.id == current_user.id:
        flash("You cannot disable your own account.", "danger")
    else:
        user.is_active_account = not user.is_active_account
        audit("admin.user_enabled" if user.is_active_account else "admin.user_disabled", current_user, "user", user.id)
        db.session.commit()
        flash(f"Account {'enabled' if user.is_active_account else 'disabled'}.", "success")
    return redirect(request.referrer or url_for("admin.users"))


@bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    form = CategoryForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        if Category.query.filter(func.lower(Category.name) == name.lower()).first() or Category.query.filter_by(slug=_slug(name)).first():
            flash("A category with that name already exists.", "danger")
        else:
            cat = Category(name=name, slug=_slug(name), description=(form.description.data or "").strip() or None)
            db.session.add(cat)
            db.session.flush()
            audit("admin.category_created", current_user, "category", cat.id, name)
            db.session.commit()
            flash("Category added.", "success")
        return redirect(url_for("admin.categories"))
    rows = [(c, KnowledgeRecord.query.filter_by(category_id=c.id).count()) for c in Category.query.order_by(Category.name)]
    return render_template("admin/categories.html", form=form, rows=rows)


@bp.route("/categories/<int:cat_id>/toggle", methods=["POST"])
@admin_required
def toggle_category(cat_id):
    cat = db.session.get(Category, cat_id) or abort(404)
    cat.is_active = not cat.is_active
    audit("admin.category_toggled", current_user, "category", cat.id, str(cat.is_active))
    db.session.commit()
    return redirect(url_for("admin.categories"))


@bp.route("/categories/<int:cat_id>/delete", methods=["POST"])
@admin_required
def delete_category(cat_id):
    cat = db.session.get(Category, cat_id) or abort(404)
    if KnowledgeRecord.query.filter_by(category_id=cat.id).count():
        flash("This category has records. Deactivate it instead of deleting.", "danger")
    else:
        audit("admin.category_deleted", current_user, "category", cat.id, cat.name)
        db.session.delete(cat)
        db.session.commit()
        flash("Category deleted.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/audit")
@admin_required
def audit_log():
    page = max(request.args.get("page", 1, type=int), 1)
    action = (request.args.get("action") or "").strip()
    q = AuditLog.query
    if action:
        q = q.filter(AuditLog.action.like(f"{action}%"))
    pag = q.order_by(AuditLog.id.desc()).paginate(page=page, per_page=30, error_out=False)
    reviews = Review.query.order_by(Review.id.desc()).limit(20).all()
    return render_template("admin/audit.html", pag=pag, reviews=reviews, action=action)


@bp.route("/health")
@admin_required
def health():
    failed = ProcessingJob.query.filter_by(status=JobStatus.FAILED).order_by(ProcessingJob.id.desc()).limit(25).all()
    ctx = {"ffmpeg": media.ffmpeg_available(), "transcription": transcription.status(),
           "llm": llm.llm_configured(), "translation": llm.translation_configured(),
           "index": retrieval.index_health(), "failed": failed,
           "job_counts": dict(db.session.query(ProcessingJob.status, func.count()).group_by(ProcessingJob.status).all())}
    return render_template("admin/health.html", **ctx)


@bp.route("/reindex", methods=["POST"])
@admin_required
def reindex():
    result = retrieval.reindex_all()
    audit("admin.reindex", current_user, detail=str(result))
    db.session.commit()
    flash(f"Reindex finished: {result}", "success" if result.get("ok") else "danger")
    return redirect(url_for("admin.health"))


@bp.route("/messages")
@admin_required
def messages():
    rows = ContactMessage.query.order_by(ContactMessage.is_resolved, ContactMessage.id.desc()).limit(100).all()
    return render_template("admin/messages.html", rows=rows)


@bp.route("/messages/<int:msg_id>/resolve", methods=["POST"])
@admin_required
def resolve_message(msg_id):
    msg = db.session.get(ContactMessage, msg_id) or abort(404)
    msg.is_resolved = True
    db.session.commit()
    return redirect(url_for("admin.messages"))
