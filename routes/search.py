from flask import Blueprint, render_template, request, g, current_app

from database import get_db
from services.vector_index import search as vector_search
from services.ai_pipeline import generate_rag_answer, AIPipelineError

bp = Blueprint("search", __name__)


@bp.route("/search")
def search_page():
    db = get_db()
    query = request.args.get("q", "").strip()
    district_id = request.args.get("district_id") or None
    category_id = request.args.get("category_id") or None

    results = []
    if query:
        results = vector_search(db, g.current_user, query, top_k=10,
                                 district_id=district_id, category_id=category_id)

    districts = db.execute("SELECT * FROM districts ORDER BY name").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    return render_template(
        "search.html", query=query, results=results, districts=districts,
        categories=categories, selected_district=district_id, selected_category=category_id,
    )


@bp.route("/ask", methods=["GET", "POST"])
def ask():
    answer = None
    sources = []
    question = ""
    error = None
    is_demo = False

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            db = get_db()
            hits = vector_search(db, g.current_user, question, top_k=4)
            context_chunks = [
                {
                    "knowledge_id": h["knowledge_id"],
                    "title": h["title"],
                    "summary": h["summary"] or "",
                    "status": h["status"],
                }
                for h in hits
            ]
            try:
                result = generate_rag_answer(question, context_chunks, current_app.config)
                answer = result["answer"]
                is_demo = result["is_demo"]
                sources = hits
            except AIPipelineError as exc:
                error = str(exc)

    return render_template(
        "ask.html", answer=answer, sources=sources, question=question,
        error=error, is_demo=is_demo,
    )
