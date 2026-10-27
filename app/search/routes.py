from flask import abort, current_app, jsonify, render_template, request, send_file, url_for
from flask_login import current_user

from ..extensions import db, limiter
from ..models import Category, KnowledgeRecord, LANGUAGES, UTTARAKHAND_DISTRICTS
from ..services import media, retrieval
from ..utils import can_view_media, can_view_record
from . import bp


def _filters_from_request():
    cat = request.args.get("category", type=int)
    lang = request.args.get("language", "")
    district = request.args.get("district", "")
    ctype = request.args.get("type", "")
    return {
        "category_id": cat if cat and db.session.get(Category, cat) else None,
        "language": lang if lang in dict(LANGUAGES) else "",
        "district": district if district in UTTARAKHAND_DISTRICTS else "",
        "content_type": ctype if ctype in ("text", "media", "audio", "video") else "",
    }


@bp.route("/explore")
@limiter.limit("60 per minute")
def explore():
    q = (request.args.get("q") or "").strip()[:200]
    page = max(request.args.get("page", 1, type=int), 1)
    filters = _filters_from_request()
    result = retrieval.search_records(q, filters, page, current_app.config["ITEMS_PER_PAGE"])
    return render_template("explore.html", q=q, filters=filters, result=result,
                           categories=Category.query.filter_by(is_active=True).order_by(Category.name).all(),
                           districts=UTTARAKHAND_DISTRICTS)


@bp.route("/api/search")
@limiter.limit("60 per minute")
def api_search():
    """JSON search over approved public records only."""
    q = (request.args.get("q") or "").strip()[:200]
    result = retrieval.search_records(q, _filters_from_request(), max(request.args.get("page", 1, type=int), 1), 10)
    return jsonify({"mode": result["mode"], "total": result["pagination"].total, "results": [
        {"id": r.id, "title": r.title, "category": r.category.name, "language": r.language_label,
         "district": r.district, "url": url_for("search.record_detail", record_id=r.id)} for r in result["records"]]})


@bp.route("/record/<int:record_id>")
def record_detail(record_id):
    record = db.session.get(KnowledgeRecord, record_id)
    if record is None or not can_view_record(record, current_user):
        abort(404)  # do not reveal whether a private/pending record exists
    related = retrieval.related_records(record) if record.is_publicly_visible else []
    return render_template("record_detail.html", record=record, related=related,
                           is_preview=not record.is_publicly_visible)


@bp.route("/media/<int:asset_id>")
def serve_media(asset_id):
    from ..models import MediaAsset
    asset = db.session.get(MediaAsset, asset_id)
    if asset is None or not can_view_media(asset, current_user):
        abort(404)
    path = media.asset_path(asset)
    if not path.exists():
        abort(404)
    resp = send_file(path, mimetype=asset.mime_type, conditional=True, download_name=asset.original_filename,
                     as_attachment=asset.kind == "document")
    resp.headers["Cache-Control"] = "public, max-age=3600" if asset.record.is_publicly_visible else "private, no-store"
    return resp
