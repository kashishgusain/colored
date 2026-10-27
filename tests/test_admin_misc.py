from app.extensions import db
from app.models import Category, ContactMessage, JobStatus, KnowledgeRecord, ProcessingJob, Role, Status, User
from conftest import login, make_record, make_user


def test_dashboard_statistics_match_database(client, users):
    make_record(users["con"], status=Status.APPROVED)
    make_record(users["con"], status=Status.APPROVED, is_public=False)
    make_record(users["con"], status=Status.PENDING)
    make_record(users["con"], status=Status.PENDING)
    make_record(users["con"], status=Status.PENDING)
    rej = make_record(users["con"], status=Status.REJECTED)
    db.session.add(ProcessingJob(record_id=rej.id, status=JobStatus.FAILED, error_code="X", error_message="boom"))
    db.session.add(ProcessingJob(record_id=rej.id, status=JobStatus.SUCCEEDED))
    db.session.commit()
    login(client, "admin")
    html = client.get("/admin/").data.decode()
    import re
    tiles = {m[1]: int(m[0]) for m in re.findall(r'class="num">(\d+)</div><div class="lbl">([^<]+)<', html)}
    assert tiles == {"Registered users": 5, "Contributions": 6, "Approved": 2, "Pending review": 3, "Rejected": 1,
                     "Needs revision": 0, "Public records": 1, "Failed AI jobs": 1}


def test_landing_stats_are_real_and_empty_state_honest(client, users):
    html = client.get("/").data.decode()
    assert "The archive is just opening" in html and "approved public records" not in html
    make_record(users["con"], status=Status.APPROVED)
    make_record(users["con"], title="Hidden private", status=Status.APPROVED, is_public=False)
    html = client.get("/").data.decode()
    assert 'class="num">1</div><div class="lbl">approved public records' in html and "Hidden private" not in html


def test_admin_pages_render(client, users):
    login(client, "admin")
    for url in ("/admin/users", "/admin/users?q=con&role=contributor", "/admin/categories", "/admin/audit", "/admin/audit?action=user.",
                "/admin/health", "/admin/messages"):
        assert client.get(url).status_code == 200, url


def test_category_management(client, users):
    login(client, "admin")
    client.post("/admin/categories", data={"name": "Local Crafts", "description": "Weaving, ringal baskets"})
    cat = Category.query.filter_by(slug="local-crafts").one()
    client.post("/admin/categories", data={"name": "local crafts", "description": ""})
    assert Category.query.filter_by(slug="local-crafts").count() == 1
    client.post(f"/admin/categories/{cat.id}/toggle")
    assert not db.session.get(Category, cat.id).is_active
    client.post(f"/admin/categories/{cat.id}/delete")
    assert db.session.get(Category, cat.id) is None
    used = Category.query.filter_by(slug="traditions").one()
    make_record(users["con"])
    client.post(f"/admin/categories/{used.id}/delete")
    assert db.session.get(Category, used.id) is not None


def test_user_disable_blocks_login_and_self_disable_blocked(client, users):
    login(client, "admin")
    client.post(f"/admin/users/{users['con'].id}/active")
    client.post(f"/admin/users/{users['admin'].id}/active")
    assert not db.session.get(User, users["con"].id).is_active_account and db.session.get(User, users["admin"].id).is_active_account


def test_contact_form_saves_message(client):
    r = client.post("/contact", data={"name": "Ravi", "email": "ravi@example.org", "subject": "Hello team",
                                      "message": "I would like to help record songs."}, follow_redirects=True)
    assert b"received" in r.data and ContactMessage.query.count() == 1


def test_health_reports_missing_providers(client, users):
    login(client, "admin")
    html = client.get("/admin/health").data.decode()
    assert "not ready" in html and "not configured" in html


def test_admin_reindex_post(client, users):
    login(client, "admin")
    assert client.post("/admin/reindex", follow_redirects=True).status_code == 200
    login_c = client
    login_c.post("/auth/logout")
    login(client, "contrib")
    assert client.post("/admin/reindex").status_code == 403


def test_cli_create_admin_is_interactive_and_validates(app, monkeypatch):
    import getpass
    from conftest import PASSWORD
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": PASSWORD)
    runner = app.test_cli_runner()
    res = runner.invoke(args=["create-admin", "--username", "root1", "--email", "root@example.org", "--name", "Root"])
    assert res.exit_code == 0, res.output
    assert User.query.filter_by(username="root1").one().role == Role.ADMIN
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "weak")
    res = runner.invoke(args=["create-admin", "--username", "root2", "--email", "r2@example.org", "--name", "R"])
    assert res.exit_code != 0 and User.query.filter_by(username="root2").first() is None
