import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port,
            debug=app.config["APP_ENV"] == "development" and os.environ.get("FLASK_DEBUG") == "1")
