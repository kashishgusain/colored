import json
import secrets

from flask import jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user

from ..extensions import db, limiter
from ..models import ChatMessage, ChatSession
from ..services import llm, rag
from . import bp

ANON_KEY = "chat_anon_key"
SESSION_ID = "chat_session_id"


def _anon_key():
    if ANON_KEY not in session:
        session[ANON_KEY] = secrets.token_urlsafe(24)
    return session[ANON_KEY]


def _owned(chat: ChatSession | None) -> bool:
    if chat is None:
        return False
    if current_user.is_authenticated:
        return chat.user_id == current_user.id
    return chat.user_id is None and chat.anon_key == session.get(ANON_KEY)


def _current_session(create=False):
    chat = db.session.get(ChatSession, session.get(SESSION_ID)) if session.get(SESSION_ID) else None
    if chat and _owned(chat):
        return chat
    if current_user.is_authenticated:  # resume the latest conversation
        chat = (ChatSession.query.filter_by(user_id=current_user.id).order_by(ChatSession.updated_at.desc()).first())
        if chat:
            session[SESSION_ID] = chat.id
            return chat
    if create:
        chat = ChatSession(user_id=current_user.id if current_user.is_authenticated else None,
                           anon_key=None if current_user.is_authenticated else _anon_key())
        db.session.add(chat)
        db.session.commit()
        session[SESSION_ID] = chat.id
        return chat
    return None


@bp.route("/")
def page():
    chat = _current_session()
    history = []
    if current_user.is_authenticated:
        history = (ChatSession.query.filter_by(user_id=current_user.id)
                   .order_by(ChatSession.updated_at.desc()).limit(15).all())
    return render_template("chat.html", chat=chat, history=history, ai_ready=llm.llm_configured())


@bp.route("/new", methods=["POST"])
def new():
    session.pop(SESSION_ID, None)
    if current_user.is_authenticated:  # force a fresh conversation instead of resuming the last one
        chat = ChatSession(user_id=current_user.id)
    else:
        chat = ChatSession(anon_key=_anon_key())
    db.session.add(chat)
    db.session.commit()
    session[SESSION_ID] = chat.id
    return redirect(url_for("chatbot.page"))


@bp.route("/open/<int:session_id>", methods=["POST"])
def open_session(session_id):
    chat = db.session.get(ChatSession, session_id)
    if _owned(chat):
        session[SESSION_ID] = chat.id
    return redirect(url_for("chatbot.page"))


@bp.route("/ask", methods=["POST"])
@limiter.limit("20 per minute")
def ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if len(question) < 3:
        return jsonify({"error": "Please type a question of at least 3 characters."}), 400
    if len(question) > 800:
        return jsonify({"error": "Please keep the question under 800 characters."}), 400
    chat = _current_session(create=True)
    result = rag.answer_question(question)
    if chat.title == "New conversation":
        chat.title = question[:60]
    db.session.add(ChatMessage(session_id=chat.id, role="user", content=question))
    ids = sorted({s["record_id"] for s in result["sources"]})
    db.session.add(ChatMessage(
        session_id=chat.id, role="assistant", content=result["answer"], mode=result["mode"],
        sources_json=json.dumps(result["sources"], ensure_ascii=False) if result["sources"] else None,
        source_record_ids=("," + ",".join(map(str, ids)) + ",") if ids else None))
    db.session.commit()
    return jsonify({"answer": result["answer"], "mode": result["mode"], "sources": result["sources"],
                    "note": result.get("note")})
