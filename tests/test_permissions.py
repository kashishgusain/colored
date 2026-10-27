import pytest

from app.extensions import db
from app.models import Role, User
from conftest import login, make_record


@pytest.mark.parametrize("url", ["/dashboard", "/contribute/new", "/moderation/", "/admin/", "/admin/users"])
def test_anonymous_redirected_to_login(client, url):
    r = client.get(url)
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


@pytest.mark.parametrize("who,url,code", [
    ("pubuser", "/contribute/new", 403), ("pubuser", "/moderation/", 403), ("contrib", "/moderation/", 403),
    ("contrib", "/admin/", 403), ("steward", "/admin/", 403), ("steward", "/moderation/", 200),
    ("admin", "/admin/", 200), ("contrib", "/contribute/new", 200)])
def test_role_matrix(client, users, who, url, code):
    login(client, who)
    assert client.get(url).status_code == code


def test_non_admin_cannot_change_roles_by_direct_post(client, users):
    login(client, "contrib")
    r = client.post(f"/admin/users/{users['con'].id}/role", data={"role": "admin"})
    assert r.status_code == 403
    assert db.session.get(User, users["con"].id).role == Role.CONTRIBUTOR


def test_admin_cannot_change_own_role_but_can_change_others(client, users):
    login(client, "admin")
    client.post(f"/admin/users/{users['admin'].id}/role", data={"role": "public_user"})
    assert db.session.get(User, users["admin"].id).role == Role.ADMIN
    client.post(f"/admin/users/{users['con'].id}/role", data={"role": "steward"})
    assert db.session.get(User, users["con"].id).role == Role.STEWARD
    assert client.post(f"/admin/users/{users['con'].id}/role", data={"role": "superuser"}).status_code == 400


def test_contributor_cannot_manage_another_users_record(client, users):
    rec = make_record(users["con"])
    login(client, "contrib2")
    for method, url in (("get", f"/contribute/{rec.id}"), ("get", f"/contribute/{rec.id}/edit"),
                        ("post", f"/contribute/{rec.id}/submit"), ("post", f"/contribute/{rec.id}/delete")):
        assert getattr(client, method)(url).status_code == 404


def test_security_headers(client):
    r = client.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff" and "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


def test_error_pages_do_not_leak(client):
    r = client.get("/definitely-missing")
    assert r.status_code == 404 and b"Traceback" not in r.data and b"Page not found" in r.data
