import json
import os
import threading
import uuid

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g,
    current_app, jsonify, send_from_directory
)

from database import get_db
from utils import login_required, allowed_file, next_knowledge_id, CATEGORY_CODES
from services.ai_pipeline import (
    extract_audio_if_needed, transcribe_audio, translate_and_extract,
    embed_text, AIPipelineError, VIDEO_EXTENSIONS,
)

bp = Blueprint("upload", __name__)


@bp.route("/record-my-knowledge", methods=["GET", "POST"])
@login_required
def record_knowledge():
    db = get_db()
    districts = db.execute("SELECT * FROM districts ORDER BY name").fetchall()

    if request.method == "POST":
        file = request.files.get("media")
        district_id = request.form.get("district_id")
        community = request.form.get("community", "").strip()
        access_level = request.form.get("access_level", "public")

        if not file or file.filename == "":
            flash("Please choose a video or audio file to upload.", "error")
            return render_template("upload.html", districts=districts)
        if not allowed_file(file.filename):
            flash("That file type isn't supported. Use MP4, MOV, WebM, MP3, WAV, or M4A.", "error")
            return render_template("upload.html", districts=districts)
        if not district_id:
            flash("Please choose a district.", "error")
            return render_template("upload.html", districts=districts)

        ext = file.filename.rsplit(".", 1)[1].lower()
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
        filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name)
        file.save(filepath)

        cur = db.execute(
            """INSERT INTO knowledge_records
               (district_id, community, access_level, contributor_id, media_path, status)
               VALUES (?, ?, ?, ?, ?, 'processing')""",
            (district_id, community or None, access_level, g.current_user["id"], stored_name),
        )
        db.commit()
        record_id = cur.lastrowid

        app_obj = current_app._get_current_object()
        thread = threading.Thread(target=process_upload, args=(app_obj, record_id, filepath), daemon=True)
        thread.start()

        return redirect(url_for("upload.status_page", record_id=record_id))

    return render_template("upload.html", districts=districts)


@bp.route("/record-my-knowledge/status/<int:record_id>")
@login_required
def status_page(record_id):
    db = get_db()
    record = db.execute("SELECT * FROM knowledge_records WHERE id = ?", (record_id,)).fetchone()
    if record is None or record["contributor_id"] != g.current_user["id"]:
        flash("Record not found.", "error")
        return redirect(url_for("upload.record_knowledge"))
    return render_template("status.html", record=record)


@bp.route("/api/status/<int:record_id>")
@login_required
def status_json(record_id):
    db = get_db()
    record = db.execute("SELECT * FROM knowledge_records WHERE id = ?", (record_id,)).fetchone()
    if record is None or record["contributor_id"] != g.current_user["id"]:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "status": record["status"],
        "knowledge_id": record["knowledge_id"],
        "error_message": record["error_message"],
        "is_demo_ai": bool(record["is_demo_ai"]),
    })


@bp.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    # Served only to logged-in users; real deployments should put this behind
    # a signed-URL object store rather than a static Flask route.
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


def _match_category(db, category_guess):
    if not category_guess:
        return None
    guess = category_guess.strip().lower()
    for name in CATEGORY_CODES:
        if name.lower() == guess:
            row = db.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
            return row["id"] if row else None
    return None


def process_upload(app, record_id, filepath):
    """Runs in a background thread with its own app context."""
    with app.app_context():
        db = get_db()

        def fail(message):
            db.execute(
                "UPDATE knowledge_records SET status = 'failed', error_message = ? WHERE id = ?",
                (message, record_id),
            )
            db.commit()

        try:
            audio_path = filepath
            ext = filepath.rsplit(".", 1)[-1].lower()
            if ext in VIDEO_EXTENSIONS:
                dest = filepath.rsplit(".", 1)[0] + ".wav"
                audio_path = extract_audio_if_needed(filepath, dest)

            transcript_result = transcribe_audio(audio_path, app.config)
            db.execute(
                "UPDATE knowledge_records SET original_transcript = ?, language = ? WHERE id = ?",
                (transcript_result["transcript"], transcript_result["language"], record_id),
            )
            db.commit()

            extraction = translate_and_extract(transcript_result["transcript"], app.config)

            record = db.execute("SELECT * FROM knowledge_records WHERE id = ?", (record_id,)).fetchone()
            district = db.execute("SELECT * FROM districts WHERE id = ?", (record["district_id"],)).fetchone()
            category_id = _match_category(db, extraction.get("category_guess", ""))
            category_name = extraction.get("category_guess") or "Vanishing Skills"

            embedding = embed_text(
                (extraction.get("summary", "") or "") + " " +
                (extraction.get("translation_en", "") or "") + " " +
                " ".join(extraction.get("keywords", []) or [])
            )

            knowledge_id = next_knowledge_id(db, district["name"] if district else "Unknown", category_name)
            is_demo = transcript_result["is_demo"] or extraction.get("is_demo", False)

            db.execute(
                """UPDATE knowledge_records SET
                    knowledge_id = ?, title = ?, translation_en = ?, materials = ?, tools = ?,
                    steps = ?, cultural_significance = ?, historical_context = ?, summary = ?,
                    keywords = ?, embedding = ?, category_id = ?, status = 'ai_extracted',
                    is_demo_ai = ?
                   WHERE id = ?""",
                (
                    knowledge_id,
                    extraction.get("title") or "Untitled knowledge record",
                    extraction.get("translation_en", ""),
                    json.dumps(extraction.get("materials", [])),
                    json.dumps(extraction.get("tools", [])),
                    json.dumps(extraction.get("steps", [])),
                    extraction.get("cultural_significance", ""),
                    extraction.get("historical_context", ""),
                    extraction.get("summary", ""),
                    json.dumps(extraction.get("keywords", [])),
                    json.dumps(embedding),
                    category_id,
                    1 if is_demo else 0,
                    record_id,
                ),
            )
            db.commit()
        except AIPipelineError as exc:
            fail(str(exc))
        except Exception as exc:  # noqa: BLE001 - never leave a record stuck silently
            fail(f"Unexpected error: {exc}")
