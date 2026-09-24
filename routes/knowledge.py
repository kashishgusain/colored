import json

from flask import Blueprint, render_template, request, redirect, url_for, flash, g

from database import get_db
from utils import login_required, role_required

bp = Blueprint("knowledge", __name__, url_prefix="/knowledge")


def _fetch(db, knowledge_id):
    return db.execute(
        """SELECT kr.*, d.name AS district_name, d.slug AS district_slug,
                  c.name AS category_name, u.username AS contributor_name
           FROM knowledge_records kr
           LEFT JOIN districts d ON d.id = kr.district_id
           LEFT JOIN categories c ON c.id = kr.category_id
           LEFT JOIN users u ON u.id = kr.contributor_id
           WHERE kr.knowledge_id = ?""",
        (knowledge_id,),
    ).fetchone()


def _visibility(record, user):
    """Returns (can_view, reason_if_not)."""
    is_owner = user is not None and user["id"] == record["contributor_id"]
    is_reviewer = user is not None and user["role"] in ("steward", "admin")

    if record["status"] in ("processing", "failed"):
        return (is_owner or is_reviewer), "not_ready"

    if record["status"] == "ai_extracted":
        return (is_owner or is_reviewer), "pending_review"

    # community_verified
    if record["access_level"] == "public":
        return True, None
    if user is None:
        return False, "community_only"
    if is_reviewer or is_owner:
        return True, None
    if user["community"] and user["community"] == record["community"]:
        return True, None
    return False, "community_only"


@bp.route("/<knowledge_id>")
def view(knowledge_id):
    db = get_db()
    record = _fetch(db, knowledge_id)
    if record is None:
        flash("That knowledge record doesn't exist.", "error")
        return redirect(url_for("index"))

    can_view, reason = _visibility(record, g.current_user)
    if not can_view:
        return render_template("access_denied.html", record=record, reason=reason)

    for field in ("materials", "tools", "steps", "keywords"):
        record = dict(record)
    materials = json.loads(record["materials"]) if record["materials"] else []
    tools = json.loads(record["tools"]) if record["tools"] else []
    steps = json.loads(record["steps"]) if record["steps"] else []
    keywords = json.loads(record["keywords"]) if record["keywords"] else []

    is_owner = g.current_user is not None and g.current_user["id"] == record["contributor_id"]
    can_review = g.current_user is not None and g.current_user["role"] in ("steward", "admin")

    return render_template(
        "record.html", record=record, materials=materials, tools=tools, steps=steps,
        keywords=keywords, is_owner=is_owner, can_review=can_review,
    )


@bp.route("/<knowledge_id>/review", methods=["GET", "POST"])
@login_required
def review(knowledge_id):
    db = get_db()
    record = _fetch(db, knowledge_id)
    if record is None:
        flash("That knowledge record doesn't exist.", "error")
        return redirect(url_for("index"))

    is_owner = g.current_user["id"] == record["contributor_id"]
    is_reviewer = g.current_user["role"] in ("steward", "admin")
    if not (is_owner or is_reviewer):
        flash("Only the knowledge holder or a Community Steward can edit this record.", "error")
        return redirect(url_for("knowledge.view", knowledge_id=knowledge_id))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        translation_en = request.form.get("translation_en", "").strip()
        summary = request.form.get("summary", "").strip()
        cultural_significance = request.form.get("cultural_significance", "").strip()
        historical_context = request.form.get("historical_context", "").strip()
        materials = [m.strip() for m in request.form.get("materials", "").splitlines() if m.strip()]
        tools = [t.strip() for t in request.form.get("tools", "").splitlines() if t.strip()]
        steps = [s.strip() for s in request.form.get("steps", "").splitlines() if s.strip()]

        db.execute(
            """UPDATE knowledge_records SET
                title = ?, translation_en = ?, summary = ?, cultural_significance = ?,
                historical_context = ?, materials = ?, tools = ?, steps = ?
               WHERE id = ?""",
            (title, translation_en, summary, cultural_significance, historical_context,
             json.dumps(materials), json.dumps(tools), json.dumps(steps), record["id"]),
        )
        db.commit()
        flash("Changes saved. This record is ready for Community Steward review.", "success")
        return redirect(url_for("knowledge.view", knowledge_id=knowledge_id))

    materials = "\n".join(json.loads(record["materials"])) if record["materials"] else ""
    tools = "\n".join(json.loads(record["tools"])) if record["tools"] else ""
    steps = "\n".join(json.loads(record["steps"])) if record["steps"] else ""
    return render_template("review.html", record=record, materials=materials, tools=tools, steps=steps)


@bp.route("/<knowledge_id>/approve", methods=["POST"])
@role_required("steward", "admin")
def approve(knowledge_id):
    db = get_db()
    record = _fetch(db, knowledge_id)
    if record is None:
        flash("That knowledge record doesn't exist.", "error")
        return redirect(url_for("index"))
    db.execute(
        "UPDATE knowledge_records SET status = 'community_verified', error_message = NULL WHERE id = ?",
        (record["id"],),
    )
    db.commit()
    flash(f"{record['knowledge_id']} is now Community Verified.", "success")
    return redirect(url_for("knowledge.view", knowledge_id=knowledge_id))


@bp.route("/<knowledge_id>/request-changes", methods=["POST"])
@role_required("steward", "admin")
def request_changes(knowledge_id):
    db = get_db()
    record = _fetch(db, knowledge_id)
    if record is None:
        flash("That knowledge record doesn't exist.", "error")
        return redirect(url_for("index"))
    note = request.form.get("note", "").strip() or "A Community Steward requested corrections."
    db.execute("UPDATE knowledge_records SET error_message = ? WHERE id = ?", (note, record["id"]))
    db.commit()
    flash("Feedback sent to the knowledge holder.", "info")
    return redirect(url_for("knowledge.view", knowledge_id=knowledge_id))
