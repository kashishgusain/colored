from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_

from ..extensions import db, limiter
from ..models import Role, User, audit, utcnow
from ..utils import is_safe_next
from . import bp
from .forms import ChangePasswordForm, LoginForm, ProfileForm, RegisterForm, validate_password_strength


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = RegisterForm()
    if form.validate_on_submit():
        # Role comes from the server, never from the request. Only the lowest tiers are self-service.
        role = Role.CONTRIBUTOR if form.want_to_contribute.data else Role.PUBLIC
        user = User(username=form.username.data, email=form.email.data, display_name=form.display_name.data.strip(),
                    role=role)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()
        audit("user.registered", user, "user", user.id, role)
        db.session.commit()
        login_user(user)
        flash("Welcome to LOKVAANI AI. Your account is ready.", "success")
        return redirect(url_for("main.dashboard"))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        ident = form.identifier.data.strip()
        user = User.query.filter(or_(User.username == ident, User.email == ident.lower())).first()
        if user and user.is_active_account and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            user.last_login_at = utcnow()
            audit("user.login", user, "user", user.id)
            db.session.commit()
            nxt = request.args.get("next")
            return redirect(nxt if is_safe_next(nxt) else url_for("main.dashboard"))
        audit("user.login_failed", None, "user", user.id if user else None, ident[:60])
        db.session.commit()
        flash("Username/email or password is incorrect, or the account is disabled.", "danger")
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.index"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    pw_form = ChangePasswordForm(prefix="pw")
    if request.method == "POST" and request.form.get("action") == "profile" and form.validate_on_submit():
        current_user.display_name = form.display_name.data.strip()
        current_user.bio = (form.bio.data or "").strip() or None
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("auth.profile"))
    if request.method == "POST" and request.form.get("action") == "password" and pw_form.validate_on_submit():
        if not current_user.check_password(pw_form.current.data):
            flash("Current password is incorrect.", "danger")
        else:
            problem = validate_password_strength(pw_form.new.data, current_user.username, current_user.email)
            if problem:
                flash(problem, "danger")
            else:
                current_user.set_password(pw_form.new.data)
                audit("user.password_changed", current_user, "user", current_user.id)
                db.session.commit()
                flash("Password changed.", "success")
                return redirect(url_for("auth.profile"))
    return render_template("auth/profile.html", form=form, pw_form=pw_form)


@bp.route("/become-contributor", methods=["POST"])
@login_required
def become_contributor():
    """Public users may self-upgrade to Contributor only. Higher roles are admin-assigned."""
    if current_user.role == Role.PUBLIC and request.form.get("agree") == "on":
        current_user.role = Role.CONTRIBUTOR
        audit("user.became_contributor", current_user, "user", current_user.id)
        db.session.commit()
        flash("You can now contribute knowledge.", "success")
    else:
        flash("Please accept the contributor guidelines to continue.", "warning")
    return redirect(url_for("auth.profile"))
