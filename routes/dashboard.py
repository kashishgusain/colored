from flask import Blueprint, render_template, g, redirect, url_for, flash

from database import get_db
from services.risk import RECOMMENDATIONS, compute_risk

bp = Blueprint("dashboard", __name__)


def _visible_records_filter():
    """SQL fragment + params for records the current viewer may see, for
    counts and district overviews (same rule as vector_index, applied before
    any listing is built)."""
    if g.current_user and g.current_user["role"] in ("steward", "admin"):
        return "kr.status = 'community_verified'", ()
    if g.current_user and g.current_user["community"]:
        return (
            "kr.status = 'community_verified' AND (kr.access_level = 'public' OR kr.community = ?)",
            (g.current_user["community"],),
        )
    return "kr.status = 'community_verified' AND kr.access_level = 'public'", ()


@bp.route("/explore")
def explore():
    db = get_db()
    where, params = _visible_records_filter()
    districts = db.execute(
        f"""SELECT d.*, COUNT(kr.id) AS record_count
            FROM districts d
            LEFT JOIN knowledge_records kr ON kr.district_id = d.id AND {where}
            GROUP BY d.id ORDER BY d.name""",
        params,
    ).fetchall()
    return render_template("explore.html", districts=districts)


@bp.route("/explore/<slug>")
def district_detail(slug):
    db = get_db()
    district = db.execute("SELECT * FROM districts WHERE slug = ?", (slug,)).fetchone()
    if district is None:
        flash("District not found.", "error")
        return redirect(url_for("dashboard.explore"))

    where, params = _visible_records_filter()
    records = db.execute(
        f"""SELECT kr.*, c.name AS category_name FROM knowledge_records kr
            LEFT JOIN categories c ON c.id = kr.category_id
            WHERE kr.district_id = ? AND {where}
            ORDER BY kr.created_at DESC""",
        (district["id"], *params),
    ).fetchall()

    risks = db.execute(
        "SELECT * FROM risk_assessments WHERE district_id = ? ORDER BY score DESC",
        (district["id"],),
    ).fetchall()

    return render_template("district.html", district=district, records=records, risks=risks)


@bp.route("/risk-dashboard")
def risk_dashboard():
    db = get_db()
    risks = db.execute(
        """SELECT r.*, d.name AS district_name, c.name AS category_name
           FROM risk_assessments r
           LEFT JOIN districts d ON d.id = r.district_id
           LEFT JOIN categories c ON c.id = r.category_id
           ORDER BY r.score DESC""",
    ).fetchall()

    breakdowns = {}
    for r in risks:
        _, _, breakdown = compute_risk(
            r["practitioners"], r["young_practitioners"], r["documentation_level"],
            r["frequency_trend"], r["geographic_concentration"], r["transmission_level"],
        )
        breakdowns[r["id"]] = breakdown

    return render_template(
        "dashboard.html", risks=risks, recommendations=RECOMMENDATIONS, breakdowns=breakdowns
    )
