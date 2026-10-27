import io

from app.extensions import db
from app.models import Category, JobStatus, KnowledgeRecord, MediaAsset, Status, Transcript
from app.services import media
from conftest import login, make_record, wav_bytes

FORM = {"title": "Jagar of Nanda Devi", "description": "A ritual song recorded in the village.", "category_id": "2",
        "language": "garhwali", "district": "Chamoli", "village": "Lata", "tags": "jagar, Nanda Devi",
        "attribution": "named", "is_public": "1", "consent_given": "y"}


def post_new(client, **extra):
    data = {**FORM, **extra}
    return client.post("/contribute/new", data=data, content_type="multipart/form-data")


def test_create_text_record(client, users, app):
    login(client, "contrib")
    r = post_new(client, submission_type="text", body_text="A long written story about the village spring and its guardian. " * 2)
    assert r.status_code == 302
    rec = KnowledgeRecord.query.one()
    assert rec.status == Status.DRAFT and rec.content_type == "text" and rec.owner_id == users["con"].id
    assert rec.tags == "jagar,nanda devi" and rec.consent_given and rec.consent_at
    assert rec.jobs[0].status == JobStatus.SUCCEEDED
    assert "No language-model provider is configured" in rec.jobs[0].warnings
    assert b"Retry AI suggestions" in client.get(f"/contribute/{rec.id}").data
    client.post(f"/contribute/{rec.id}/retry")
    db.session.expire_all()
    rec = KnowledgeRecord.query.one()
    assert len(rec.jobs) == 2 and rec.jobs[0].status == JobStatus.SUCCEEDED


def test_text_record_saves_ai_suggestions_separately(client, users, monkeypatch):
    from app.services import summarization

    monkeypatch.setattr(summarization, "analyze", lambda *args: {
        "summary": "A story about a village spring.",
        "tags": ["spring", "village knowledge"],
        "suggested_category": {"slug": "oral-histories", "name": "Oral Histories"},
        "metadata": {"places": ["Lata"]},
    })
    login(client, "contrib")
    post_new(client, submission_type="text", body_text="A long written story about the village spring and its guardian. " * 2)

    rec = KnowledgeRecord.query.one()
    assert rec.summary is None
    assert rec.ai_metadata["suggested_summary"] == "A story about a village spring."
    assert rec.ai_suggested_tags == "spring,village knowledge"
    assert rec.tags == "jagar,nanda devi"
    assert rec.ai_metadata["suggested_category"]["slug"] == "oral-histories"
    assert rec.ai_metadata["places"] == ["Lata"]

    page = client.get(f"/contribute/{rec.id}/edit").data
    assert b"AI summary suggestion" in page
    assert b'data-ai-action="use-summary"' in page
    assert b'data-ai-action="append-tags"' in page
    assert b'data-ai-action="use-category"' in page

    category_id = Category.query.filter_by(slug="oral-histories").one().id
    client.post(f"/contribute/{rec.id}/edit", data={
        **FORM,
        "category_id": str(category_id),
        "body_text": "A long written story about the village spring and its guardian. " * 2,
        "summary": rec.ai_metadata["suggested_summary"],
        "tags": "jagar,nanda devi,spring,village knowledge",
    })
    db.session.refresh(rec)
    assert rec.summary == "A story about a village spring."
    assert rec.category.slug == "oral-histories"
    assert rec.tags == "jagar,nanda devi,spring,village knowledge"


def test_text_record_requires_text_and_consent(client, users):
    login(client, "contrib")
    assert post_new(client, submission_type="text", body_text="too short").status_code == 200
    data = {k: v for k, v in FORM.items() if k != "consent_given"}
    r = client.post("/contribute/new", data={**data, "submission_type": "text", "body_text": "x" * 80},
                    content_type="multipart/form-data")
    assert r.status_code == 200 and KnowledgeRecord.query.count() == 0


def test_media_upload_validation(client, users, app):
    login(client, "contrib")
    bad = [("evil.exe", b"MZ\x90\x00" + b"0" * 100), ("fake.mp3", b"this is text not audio"), ("../../x.wav", b"junk"),
           ("empty.wav", b"")]
    for name, content in bad:
        r = post_new(client, submission_type="media", media_file=(io.BytesIO(content), name))
        assert r.status_code in (200, 400), name
    assert KnowledgeRecord.query.count() == 0 and MediaAsset.query.count() == 0


def test_size_limit_enforced(client, users, app):
    app.config["MAX_SIZE_BY_KIND"] = {**app.config["MAX_SIZE_BY_KIND"], "audio": 1000}
    login(client, "contrib")
    r = post_new(client, submission_type="media", media_file=(io.BytesIO(wav_bytes(1)), "big.wav"))
    assert r.status_code == 400 and KnowledgeRecord.query.count() == 0


def test_validate_upload_unit(app):
    from werkzeug.datastructures import FileStorage
    from app.services.errors import UploadError
    import pytest
    with app.test_request_context():
        ok = FileStorage(io.BytesIO(wav_bytes()), filename="Story One.WAV")
        assert media.validate_upload(ok, ("audio",))[:2] == ("audio", "wav")
        for name, data in (("a.txt", b"hi\x00there"), ("a.png", b"notpng"), ("noext", b"abc")):
            with pytest.raises(UploadError):
                media.validate_upload(FileStorage(io.BytesIO(data), filename=name), ("audio", "video", "photo", "document"))


def test_stored_file_uses_random_name_and_safe_path(client, users, app):
    login(client, "contrib")
    post_new(client, submission_type="media", media_file=(io.BytesIO(wav_bytes()), "../../../etc/passwd.wav"))
    asset = MediaAsset.query.one()
    assert "/" not in asset.stored_filename and ".." not in asset.stored_filename and asset.stored_filename.endswith(".wav")
    path = media.asset_path(asset)
    assert path.exists() and str(path).startswith(str(app.config["UPLOAD_FOLDER"]))


def test_missing_transcription_provider_gives_clear_error_not_fake_transcript(client, users):
    login(client, "contrib")
    post_new(client, submission_type="media", media_file=(io.BytesIO(wav_bytes()), "story.wav"))
    rec = KnowledgeRecord.query.one()
    job = rec.jobs[0]
    assert job.status == JobStatus.FAILED and job.error_code == "TRANSCRIPTION_NOT_CONFIGURED"
    assert "TRANSCRIPTION_PROVIDER" in job.error_message
    assert rec.transcript is None and rec.status == Status.DRAFT
    page = client.get(f"/contribute/{rec.id}").data
    assert b"Processing did not finish" in page and b"Retry processing" in page
    # cannot submit a recording that has no transcript
    client.post(f"/contribute/{rec.id}/submit")
    assert db.session.get(KnowledgeRecord, rec.id).status == Status.DRAFT


def test_processing_success_with_mocked_provider(client, users, monkeypatch):
    from app.services import transcription
    from app.services import summarization

    analysis_calls = []

    def fake_analyze(text, *args):
        analysis_calls.append(text)
        return {"summary": "A recorded folk song.", "tags": ["jagar", "nanda devi"],
                "suggested_category": {"slug": "folk-songs", "name": "Folk Songs"}, "metadata": {}}

    monkeypatch.setattr(transcription, "transcribe", lambda path, lang: {
        "text": "Yeh Garhwal ki ek purani kahani hai.", "language": "hi", "provider": "mock", "model": "mock-1"})
    monkeypatch.setattr(summarization, "analyze", fake_analyze)
    login(client, "contrib")
    post_new(client, submission_type="media", media_file=(io.BytesIO(wav_bytes()), "story.wav"))
    rec = KnowledgeRecord.query.one()
    assert rec.jobs[0].status == JobStatus.SUCCEEDED and rec.transcript.original_text.startswith("Yeh Garhwal")
    assert rec.status == Status.DRAFT and "Speech models do not officially support" in (rec.jobs[0].warnings or "")
    assert "Translation to Hindi skipped" in rec.jobs[0].warnings  # no provider: skipped, not faked
    assert rec.translations == [] and rec.summary is None
    assert "Yeh Garhwal ki ek purani kahani hai." in analysis_calls[0]
    assert "A ritual song recorded in the village." in analysis_calls[0]
    assert rec.ai_metadata["suggested_summary"] == "A recorded folk song."
    assert rec.ai_metadata["suggested_category"]["slug"] == "folk-songs"
    assert rec.tags == "jagar,nanda devi"


def test_processing_failure_is_recorded_and_retry_works(client, users, monkeypatch):
    from app.services import transcription
    from app.services.errors import ServiceError
    calls = {"n": 0}

    def flaky(path, lang):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ServiceError("model download failed", code="WHISPER_MODEL_LOAD_FAILED")
        return {"text": "Kahani ka pehla bhag.", "language": "hi", "provider": "mock", "model": "m"}
    monkeypatch.setattr(transcription, "transcribe", flaky)
    login(client, "contrib")
    post_new(client, submission_type="media", media_file=(io.BytesIO(wav_bytes()), "s.wav"))
    rec = KnowledgeRecord.query.one()
    assert rec.jobs[0].error_code == "WHISPER_MODEL_LOAD_FAILED"
    client.post(f"/contribute/{rec.id}/retry")
    db.session.expire_all()
    rec = KnowledgeRecord.query.one()
    assert rec.jobs[0].status == JobStatus.SUCCEEDED and len(rec.jobs) == 2 and rec.transcript.original_text


def test_corrections_preserve_original_transcript(client, users):
    rec = make_record(users["con"])
    rec.content_type = "audio"
    db.session.add(Transcript(record_id=rec.id, original_text="galat shabd", source="mock"))
    db.session.commit()
    login(client, "contrib")
    data = {**FORM, "transcript_text": "sahi shabd", "translation_en": "correct words", "is_public": "1", "body_text": ""}
    r = client.post(f"/contribute/{rec.id}/edit", data=data)
    assert r.status_code == 302
    db.session.expire_all()
    rec = db.session.get(KnowledgeRecord, rec.id)
    assert rec.transcript.original_text == "galat shabd" and rec.transcript_text == "sahi shabd"
    assert rec.translation_for("en").text == "correct words" and rec.translation_for("en").is_human_edited


def test_update_record_metadata(client, users):
    rec = make_record(users["con"])
    login(client, "contrib")
    data = {**FORM, "title": "Harela (updated)", "body_text": "Updated text for Harela. " * 5, "category_id": str(rec.category_id)}
    client.post(f"/contribute/{rec.id}/edit", data=data)
    db.session.expire_all()
    r = db.session.get(KnowledgeRecord, rec.id)
    assert r.title == "Harela (updated)" and r.language == "garhwali" and r.district == "Chamoli"


def test_submit_withdraw_delete_flow(client, users, app):
    rec = make_record(users["con"])
    login(client, "contrib")
    client.post(f"/contribute/{rec.id}/submit")
    assert db.session.get(KnowledgeRecord, rec.id).status == Status.PENDING
    client.post(f"/contribute/{rec.id}/withdraw")
    r = db.session.get(KnowledgeRecord, rec.id)
    assert r.status == Status.WITHDRAWN and not r.is_public and r.withdrawn_at
    client.post(f"/contribute/{rec.id}/delete")
    assert db.session.get(KnowledgeRecord, rec.id) is None
