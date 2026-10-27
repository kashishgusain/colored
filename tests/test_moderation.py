import pytest

from app.extensions import db
from app.models import AuditLog, InvalidTransition, KnowledgeRecord, Review, Status
from conftest import approve_via_ui, login, make_record


def test_state_machine_rules(users):
    rec = make_record(users["con"])
    for bad in (Status.APPROVED, Status.REJECTED, Status.NEEDS_REVISION):
        with pytest.raises(InvalidTransition):
            rec.transition(bad)
    rec.transition(Status.PROCESSING)
    rec.transition(Status.DRAFT)
    rec.transition(Status.PENDING)
    rec.transition(Status.APPROVED)
    with pytest.raises(InvalidTransition):
        rec.transition(Status.REJECTED)
    rec.status = Status.REJECTED
    with pytest.raises(InvalidTransition):
        rec.transition(Status.APPROVED)


def test_approve_records_review_and_audit(client, users):
    rec = make_record(users["con"], status=Status.PENDING)
    r = approve_via_ui(client, "steward", rec.id)
    assert r.status_code == 200
    db.session.expire_all()
    rec = db.session.get(KnowledgeRecord, rec.id)
    assert rec.status == Status.APPROVED and rec.verified_by_id == users["stew"].id and rec.approved_at
    rv = Review.query.one()
    assert (rv.decision, rv.from_status, rv.to_status, rv.reviewer_id, rv.comment) == \
           ("approved", "pending_review", "approved", users["stew"].id, "Verified.")
    assert AuditLog.query.filter_by(action="review.approved").count() == 1


def test_reject_and_revision_require_comment(client, users):
    rec = make_record(users["con"], status=Status.PENDING)
    login(client, "steward")
    client.post(f"/moderation/{rec.id}/decision", data={"decision": "reject", "comment": ""})
    client.post(f"/moderation/{rec.id}/decision", data={"decision": "revise", "comment": ""})
    assert db.session.get(KnowledgeRecord, rec.id).status == Status.PENDING and Review.query.count() == 0
    client.post(f"/moderation/{rec.id}/decision", data={"decision": "revise", "comment": "Please fix the village name."})
    assert db.session.get(KnowledgeRecord, rec.id).status == Status.NEEDS_REVISION
    # contributor sees the note and can resubmit
    client.post("/auth/logout")
    login(client, "contrib")
    assert b"Please fix the village name." in client.get(f"/contribute/{rec.id}").data
    client.post(f"/contribute/{rec.id}/submit")
    assert db.session.get(KnowledgeRecord, rec.id).status == Status.PENDING
    client.post("/auth/logout")
    login(client, "steward")
    client.post(f"/moderation/{rec.id}/decision", data={"decision": "reject", "comment": "Not original material."})
    assert db.session.get(KnowledgeRecord, rec.id).status == Status.REJECTED
    assert [r.decision for r in Review.query.order_by(Review.id)] == ["needs_revision", "rejected"]


def test_cannot_decide_on_draft(client, users):
    rec = make_record(users["con"])
    login(client, "steward")
    client.post(f"/moderation/{rec.id}/decision", data={"decision": "approve", "comment": ""})
    assert db.session.get(KnowledgeRecord, rec.id).status == Status.DRAFT


def test_steward_cannot_review_own_submission(client, users):
    rec = make_record(users["stew"], status=Status.PENDING)
    login(client, "steward")
    client.post(f"/moderation/{rec.id}/decision", data={"decision": "approve", "comment": ""})
    assert db.session.get(KnowledgeRecord, rec.id).status == Status.PENDING


def test_contributor_cannot_post_decision(client, users):
    rec = make_record(users["con"], status=Status.PENDING)
    login(client, "contrib")
    assert client.post(f"/moderation/{rec.id}/decision", data={"decision": "approve"}).status_code == 403
    assert db.session.get(KnowledgeRecord, rec.id).status == Status.PENDING


def test_record_without_consent_cannot_be_approved(client, users):
    rec = make_record(users["con"], status=Status.PENDING, consent=False)
    approve_via_ui(client, "steward", rec.id)
    assert db.session.get(KnowledgeRecord, rec.id).status == Status.PENDING


def test_steward_edit_and_note(client, users):
    rec = make_record(users["con"], status=Status.PENDING)
    login(client, "steward")
    client.post(f"/moderation/{rec.id}/edit", data={"title": "Harela, corrected", "description": "Better description here.",
                                                    "category_id": rec.category_id, "tags": "harela", "body_text": "Edited body. " * 8, "summary": ""})
    assert db.session.get(KnowledgeRecord, rec.id).title == "Harela, corrected"
    client.post(f"/moderation/{rec.id}/decision", data={"decision": "comment", "comment": "Asked elder to confirm."})
    assert Review.query.one().decision == "comment" and db.session.get(KnowledgeRecord, rec.id).status == Status.PENDING
