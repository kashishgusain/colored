import io
import struct
import wave

import pytest

from app import create_app
from app.extensions import db
from app.models import Category, DEFAULT_CATEGORIES, KnowledgeRecord, Role, Status, User, utcnow

PASSWORD = "Himalaya-Pass-2026!"


@pytest.fixture()
def app(tmp_path):
    app = create_app("testing", {"UPLOAD_FOLDER": str(tmp_path / "uploads"), "VECTOR_DIR": str(tmp_path / "chroma")})
    with app.app_context():
        db.create_all()
        for slug, name, desc in DEFAULT_CATEGORIES:
            db.session.add(Category(slug=slug, name=name, description=desc))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(username, role=Role.CONTRIBUTOR):
    u = User(username=username, email=f"{username}@example.org", display_name=username.title(), role=role)
    u.set_password(PASSWORD)
    db.session.add(u)
    db.session.commit()
    return u


def login(client, username, password=PASSWORD):
    return client.post("/auth/login", data={"identifier": username, "password": password}, follow_redirects=True)


@pytest.fixture()
def users(app):
    return {"pub": make_user("pubuser", Role.PUBLIC), "con": make_user("contrib", Role.CONTRIBUTOR),
            "con2": make_user("contrib2", Role.CONTRIBUTOR), "stew": make_user("steward", Role.STEWARD),
            "admin": make_user("admin", Role.ADMIN)}


def make_record(owner, title="Harela festival story", text=None, status=Status.DRAFT, is_public=True, language="kumaoni",
                category_slug="traditions", consent=True):
    cat = Category.query.filter_by(slug=category_slug).first()
    text = text or ("Harela is celebrated in Kumaon at the start of the monsoon. Families sow seven grains in a basket "
                    "and cut the green shoots ten days later to place before the household deities.")
    r = KnowledgeRecord(owner_id=owner.id, category_id=cat.id, title=title, description="How Harela is celebrated.",
                        body_text=text, language=language, district="Almora", tags="harela,festival", consent_given=consent,
                        consent_at=utcnow(), is_public=is_public, status=Status.DRAFT)
    db.session.add(r)
    db.session.commit()
    if status != Status.DRAFT:
        r.status = status
        if status == Status.APPROVED:
            r.approved_at = utcnow()
        db.session.commit()
    return r


def approve_via_ui(client, steward, record_id):
    login(client, steward)
    return client.post(f"/moderation/{record_id}/decision", data={"decision": "approve", "comment": "Verified."},
                       follow_redirects=True)


def wav_bytes(seconds=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<h", 0) * 16000 * seconds)
    return buf.getvalue()
