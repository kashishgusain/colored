from app.models import Role, User
from app.extensions import db
from conftest import PASSWORD, login, make_user


def test_register_and_login(client):
    r = client.post("/auth/register", data={"display_name": "Asha Rawat", "username": "asha", "email": "Asha@Example.org",
                                            "password": PASSWORD, "confirm": PASSWORD, "want_to_contribute": "y"},
                    follow_redirects=True)
    assert r.status_code == 200 and b"Welcome" in r.data
    u = User.query.filter_by(username="asha").one()
    assert u.role == Role.CONTRIBUTOR and u.email == "asha@example.org"
    client.post("/auth/logout")
    assert login(client, "asha").status_code == 200
    assert b"Hello, Asha Rawat" in client.get("/dashboard").data


def test_register_without_contribute_is_public_user(client):
    client.post("/auth/register", data={"display_name": "Bimla", "username": "bimla", "email": "b@example.org",
                                        "password": PASSWORD, "confirm": PASSWORD})
    assert User.query.filter_by(username="bimla").one().role == Role.PUBLIC


def test_cannot_self_assign_admin_at_registration(client):
    client.post("/auth/register", data={"display_name": "Evil", "username": "evil", "email": "e@example.org",
                                        "password": PASSWORD, "confirm": PASSWORD, "role": "admin", "is_admin": "1"})
    assert User.query.filter_by(username="evil").one().role == Role.PUBLIC


def test_password_is_hashed_and_policy_enforced(client, users):
    u = users["con"]
    assert u.password_hash != PASSWORD and PASSWORD not in u.password_hash and u.check_password(PASSWORD)
    assert not u.check_password("wrong")
    for bad in ("short1!", "1234567890123", "onlylettersnodigits"):
        r = client.post("/auth/register", data={"display_name": "X Y", "username": "weak", "email": "w@example.org",
                                                "password": bad, "confirm": bad})
        assert User.query.filter_by(username="weak").first() is None, bad


def test_wrong_password_and_disabled_account(client, users):
    assert b"incorrect" in login(client, "contrib", "nope-nope-nope1").data
    users["con"].is_active_account = False
    db.session.commit()
    assert b"incorrect" in login(client, "contrib").data


def test_open_redirect_blocked(client, users):
    r = client.post("/auth/login?next=//evil.example", data={"identifier": "contrib", "password": PASSWORD})
    assert r.status_code == 302 and "evil.example" not in r.headers["Location"]


def test_public_user_can_upgrade_only_to_contributor(client, users):
    login(client, "pubuser")
    client.post("/auth/become-contributor", data={"agree": "on", "role": "admin"})
    assert db.session.get(User, users["pub"].id).role == Role.CONTRIBUTOR


def test_csrf_enforced_when_enabled(tmp_path):
    from app import create_app
    app = create_app("testing", {"WTF_CSRF_ENABLED": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        r = app.test_client().post("/auth/login", data={"identifier": "a", "password": "b"})
        assert r.status_code == 400


def test_login_rate_limit(tmp_path):
    from app import create_app
    app = create_app("testing", {"RATELIMIT_ENABLED": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        c = app.test_client()
        codes = [c.post("/auth/login", data={"identifier": "a", "password": "b"}).status_code for _ in range(12)]
        assert 429 in codes
