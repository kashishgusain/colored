import re
from functools import wraps

from flask import session, g, redirect, url_for, flash, current_app

from database import get_db

DISTRICT_CODES = {
    "Almora": "ALM", "Bageshwar": "BAG", "Chamoli": "CHM", "Champawat": "CHP",
    "Dehradun": "DDN", "Haridwar": "HAR", "Nainital": "NAI", "Pauri Garhwal": "PAU",
    "Pithoragarh": "PIT", "Rudraprayag": "RUD", "Tehri Garhwal": "TEH",
    "Udham Singh Nagar": "USN", "Uttarkashi": "UTK",
}

CATEGORY_CODES = {
    "Traditional Agriculture": "AGRI", "Seed Preservation": "SEED", "Food Heritage": "FOOD",
    "Handicrafts": "CRFT", "Folk Culture": "CULT", "Traditional Architecture": "ARCH",
    "Water & Environment": "WATR", "Oral History": "HIST", "Traditional Tools": "TOOL",
    "Local Plant Knowledge": "PLNT", "Ayurveda-related Traditional Knowledge": "AYUR",
    "Festivals & Traditions": "FEST", "Vanishing Skills": "SKIL", "Local Products": "PROD",
}


def allowed_file(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_current_user():
    if "user_id" not in session:
        g.current_user = None
        return None
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    g.current_user = row
    return row


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.current_user is None:
            flash("Please log in to continue.", "info")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.current_user is None:
                flash("Please log in to continue.", "info")
                return redirect(url_for("auth.login"))
            if g.current_user["role"] not in roles:
                flash("You don't have permission to do that.", "error")
                return redirect(url_for("index"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def next_knowledge_id(db, district_name, category_name):
    d_code = DISTRICT_CODES.get(district_name, "UNK")
    c_code = CATEGORY_CODES.get(category_name, "GEN")
    prefix = f"UK-{d_code}-{c_code}-"
    row = db.execute(
        "SELECT knowledge_id FROM knowledge_records WHERE knowledge_id LIKE ? ORDER BY id DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    if row:
        last_num = int(row["knowledge_id"].rsplit("-", 1)[-1])
        num = last_num + 1
    else:
        num = 1
    return f"{prefix}{num:04d}"
