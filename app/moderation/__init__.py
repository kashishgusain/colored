from flask import Blueprint

bp = Blueprint("moderation", __name__, url_prefix="/moderation")

from . import routes  # noqa: E402,F401
