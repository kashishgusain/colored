"""Shared record-editing helpers used by contributors and stewards."""
from ..extensions import db
from ..models import Transcript, Translation


def set_transcript_text(record, text: str | None, actor) -> bool:
    """Save a human-corrected transcript. The original machine/first text is never overwritten."""
    text = (text or "").strip()
    t = record.transcript
    if t is None:
        if not text:
            return False
        db.session.add(Transcript(record_id=record.id, original_text=text, edited_text=None, source="manual",
                                  edited_by_id=getattr(actor, "id", None)))
        db.session.flush()
        db.session.refresh(record)
        return True
    current = t.edited_text if t.edited_text is not None else t.original_text
    if text == (current or "").strip():
        return False
    t.edited_text = text
    t.edited_by_id = getattr(actor, "id", None)
    return True


def set_translation(record, lang: str, text: str | None) -> bool:
    text = (text or "").strip()
    row = record.translation_for(lang)
    if row is None:
        if not text:
            return False
        db.session.add(Translation(record_id=record.id, target_language=lang, text=text, provider="manual",
                                   is_human_edited=True))
        db.session.flush()
        db.session.refresh(record)
        return True
    if text == (row.text or "").strip():
        return False
    if not text:
        db.session.delete(row)
        return True
    row.text = text
    row.is_human_edited = True
    return True
