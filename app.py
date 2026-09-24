import os

from flask import Flask, render_template, g

from config import Config
from database import register_db, init_db, get_db
from utils import load_current_user

from routes.auth import bp as auth_bp
from routes.upload import bp as upload_bp
from routes.knowledge import bp as knowledge_bp
from routes.search import bp as search_bp
from routes.dashboard import bp as dashboard_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    register_db(app)
    init_db(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(dashboard_bp)

    @app.before_request
    def _load_user():
        load_current_user()

    @app.context_processor
    def inject_globals():
        return {"current_user": g.get("current_user", None), "ai_demo_mode": app.config["AI_DEMO_MODE"]}

    @app.route("/")
    def index():
        db = get_db()
        stats = {
            "verified": db.execute(
                "SELECT COUNT(*) c FROM knowledge_records WHERE status = 'community_verified'"
            ).fetchone()["c"],
            "districts": db.execute("SELECT COUNT(*) c FROM districts").fetchone()["c"],
            "categories": db.execute("SELECT COUNT(*) c FROM categories").fetchone()["c"],
            "at_risk": db.execute(
                "SELECT COUNT(*) c FROM risk_assessments WHERE band IN ('High', 'Critical')"
            ).fetchone()["c"],
        }
        featured = db.execute(
            """SELECT kr.*, d.name AS district_name, c.name AS category_name
               FROM knowledge_records kr
               LEFT JOIN districts d ON d.id = kr.district_id
               LEFT JOIN categories c ON c.id = kr.category_id
               WHERE kr.status = 'community_verified' AND kr.access_level = 'public'
               ORDER BY kr.created_at DESC LIMIT 3"""
        ).fetchall()
        return render_template("index.html", stats=stats, featured=featured)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors.html", code=404, message="That page doesn't exist."), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors.html", code=500, message="Something went wrong on our end."), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"], port=5000)
