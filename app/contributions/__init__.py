from flask import Blueprint

bp = Blueprint("contributions", __name__, url_prefix="/contribute")

from . import routes  # noqa: E402,F401
