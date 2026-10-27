from flask import Blueprint

bp = Blueprint("chatbot", __name__, url_prefix="/chat")

from . import routes  # noqa: E402,F401
