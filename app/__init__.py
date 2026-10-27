"""LOKVAANI AI application factory."""
import logging
import secrets
from pathlib import Path

import click
from flask import Flask, render_template, request, jsonify

from config import CONFIGS, BASE_DIR
from .extensions import csrf, db, limiter, login_manager, migrate


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    import os

    config_name = config_name or os.environ.get("APP_ENV", "development")
    cfg = CONFIGS.get(config_name, CONFIGS["development"])
    app = Flask(__name__, instance_path=str(BASE_DIR / "instance"))
    app.config.from_object(cfg)
    if overrides:
        app.config.update(overrides)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    _ensure_secret_key(app)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from . import models  # noqa: F401  (register models)
    from .admin import bp as admin_bp
    from .auth import bp as auth_bp
    from .chatbot import bp as chat_bp
    from .contributions import bp as contrib_bp
    from .main import bp as main_bp
    from .moderation import bp as mod_bp
    from .search import bp as search_bp

    for bp in (main_bp, auth_bp, contrib_bp, search_bp, chat_bp, mod_bp, admin_bp):
        app.register_blueprint(bp)

    _register_hooks(app)
    _register_errors(app)
    _register_cli(app)
    logging.basicConfig(level=logging.INFO)
    return app


def _ensure_secret_key(app: Flask) -> None:
    if app.config.get("SECRET_KEY"):
        return
    if app.config["APP_ENV"] == "production":
        raise RuntimeError("SECRET_KEY must be set in the environment for production.")
    key_file = Path(app.instance_path) / ".dev_secret_key"  # git-ignored; development only
    if key_file.exists():
        app.config["SECRET_KEY"] = key_file.read_text().strip()
    else:
        key = secrets.token_hex(32)
        key_file.write_text(key)
        app.config["SECRET_KEY"] = key


def _register_hooks(app: Flask) -> None:
    from .models import LANGUAGES, Role, Status

    @app.context_processor
    def inject_globals():
        return {"Role": Role, "Status": Status, "LANGUAGES": LANGUAGES, "APP_NAME": "LOKVAANI AI",
                "TAGLINE": "Preserve the past. Understand it. Build the future."}

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        if request.endpoint and request.endpoint.startswith(("contributions.", "moderation.", "admin.", "auth.")):
            resp.headers["Cache-Control"] = "no-store"
        if app.config["APP_ENV"] == "production":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp

    @app.template_filter("dt")
    def fmt_dt(value, fmt="%d %b %Y, %H:%M"):
        return value.strftime(fmt) if value else ""

    @app.template_filter("nl2p")
    def nl2p(text):
        from markupsafe import Markup, escape
        paras = [p.strip() for p in (text or "").replace("\r", "").split("\n\n") if p.strip()]
        return Markup("".join(f"<p>{escape(p).replace(chr(10), Markup('<br>'))}</p>" for p in paras))



def _register_errors(app: Flask) -> None:
    def wants_json():
        return request.path.startswith(("/chat/ask", "/api/")) or request.accept_mimetypes.best == "application/json"

    def handler(code, title, message):
        def _h(err):
            if wants_json():
                return jsonify({"error": title, "message": message}), code
            return render_template("errors/error.html", code=code, title=title, message=message), code
        return _h

    app.register_error_handler(400, handler(400, "Request could not be processed",
                                            "The form expired or the request was invalid. Go back, refresh the page and try again."))
    app.register_error_handler(403, handler(403, "You do not have access", "Your account is not allowed to open this page."))
    app.register_error_handler(404, handler(404, "Page not found", "We could not find what you were looking for. It may have been moved, withdrawn or never existed."))
    app.register_error_handler(413, handler(413, "File too large", "The upload is larger than the allowed size. Choose a smaller file."))
    app.register_error_handler(429, handler(429, "Too many requests", "You have made too many requests in a short time. Wait a minute and try again."))

    @app.errorhandler(500)
    def server_error(err):
        db.session.rollback()
        app.logger.exception("Unhandled server error")
        if wants_json():
            return jsonify({"error": "Server error", "message": "Something went wrong on our side."}), 500
        return render_template("errors/error.html", code=500, title="Something went wrong",
                               message="An unexpected error occurred. It has been logged. Please try again shortly."), 500


def _register_cli(app: Flask) -> None:
    import getpass
    from .models import Category, DEFAULT_CATEGORIES, Role, User, audit

    @app.cli.command("seed-categories")
    def seed_categories():
        """Create the default cultural categories (safe to run repeatedly)."""
        added = 0
        for slug, name, desc in DEFAULT_CATEGORIES:
            if not Category.query.filter_by(slug=slug).first():
                db.session.add(Category(slug=slug, name=name, description=desc))
                added += 1
        db.session.commit()
        click.echo(f"Categories ready ({added} added).")

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--name", "display_name", prompt="Display name")
    def create_admin(username, email, display_name):
        """Create an administrator. The password is typed interactively and never stored in a file."""
        from .auth.forms import validate_password_strength
        pw = getpass.getpass("Password: ")
        if pw != getpass.getpass("Repeat password: "):
            raise click.ClickException("Passwords do not match.")
        problem = validate_password_strength(pw, username, email)
        if problem:
            raise click.ClickException(problem)
        if User.query.filter((User.username == username) | (User.email == email.lower())).first():
            raise click.ClickException("A user with that username or email already exists.")
        user = User(username=username, email=email, display_name=display_name, role=Role.ADMIN)
        user.set_password(pw)
        db.session.add(user)
        audit("admin.created_via_cli", None, "user", None, username)
        db.session.commit()
        click.echo(f"Administrator '{username}' created. Sign in at /auth/login.")

    @app.cli.command("reindex")
    def reindex():
        """Rebuild the semantic index from approved public records."""
        from .services import retrieval
        click.echo(retrieval.reindex_all())

    @app.cli.command("check-ai")
    def check_ai():
        """Show which AI integrations are ready, without calling paid APIs."""
        from .services import llm, media, retrieval, transcription
        click.echo(f"FFmpeg:        {'found' if media.ffmpeg_available() else 'MISSING'}")
        click.echo(f"Transcription: {transcription.status()}")
        click.echo(f"LLM:           {'configured' if llm.llm_configured() else 'not configured (retrieval-only chatbot)'}")
        click.echo(f"Translation:   {'configured' if llm.translation_configured() else 'not configured'}")
        click.echo(f"Vector index:  {retrieval.vector_available()}")
