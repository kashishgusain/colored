from functools import wraps

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user

from .models import Role, Status


def roles_required(*roles):
    """Server-side role check. 401 -> login redirect, 403 -> forbidden page."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not current_user.is_authenticated:
                flash("Please sign in to continue.", "info")
                return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
            if current_user.role not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


contributor_required = roles_required(*Role.CAN_CONTRIBUTE)
steward_required = roles_required(*Role.CAN_REVIEW)
admin_required = roles_required(Role.ADMIN)


def is_safe_next(target: str | None) -> bool:
    return bool(target) and target.startswith("/") and not target.startswith("//") and "\\" not in target


def can_view_record(record, user) -> bool:
    """Public once approved+public; otherwise only owner, stewards and admins."""
    if record.is_publicly_visible:
        return True
    if not getattr(user, "is_authenticated", False):
        return False
    return user.id == record.owner_id or user.role in Role.CAN_REVIEW


def is_privileged_for(record, user) -> bool:
    return bool(getattr(user, "is_authenticated", False)) and (user.id == record.owner_id or user.role in Role.CAN_REVIEW)


def can_view_media(asset, user) -> bool:
    """Public records expose recordings and photos only; documents stay with the owner and reviewers."""
    rec = asset.record
    if is_privileged_for(rec, user):
        return True
    return rec.is_publicly_visible and asset.kind in ("audio", "video", "photo")


def owner_editable(record) -> bool:
    return record.status in (Status.DRAFT, Status.NEEDS_REVISION, Status.PENDING, Status.APPROVED)
