"""Database models for LOKVAANI AI."""
import json
import re
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


def utcnow() -> datetime:
    """Naive UTC timestamp (consistent across SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
class Role:
    PUBLIC = "public_user"
    CONTRIBUTOR = "contributor"
    STEWARD = "steward"
    ADMIN = "admin"
    ALL = (PUBLIC, CONTRIBUTOR, STEWARD, ADMIN)
    LABELS = {
        PUBLIC: "Public User",
        CONTRIBUTOR: "Contributor",
        STEWARD: "Community Steward",
        ADMIN: "Admin",
    }
    CAN_CONTRIBUTE = (CONTRIBUTOR, STEWARD, ADMIN)
    CAN_REVIEW = (STEWARD, ADMIN)


class Status:
    DRAFT = "draft"
    PROCESSING = "processing"
    PENDING = "pending_review"
    NEEDS_REVISION = "needs_revision"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    ALL = (DRAFT, PROCESSING, PENDING, NEEDS_REVISION, APPROVED, REJECTED, WITHDRAWN)
    LABELS = {
        DRAFT: "Draft",
        PROCESSING: "Processing",
        PENDING: "Pending Review",
        NEEDS_REVISION: "Needs Revision",
        APPROVED: "Approved",
        REJECTED: "Rejected",
        WITHDRAWN: "Withdrawn",
    }
    # Allowed transitions. Processing hands the record back to Draft so the
    # contributor can check the AI output before submitting for verification.
    TRANSITIONS = {
        DRAFT: {PROCESSING, PENDING},
        PROCESSING: {DRAFT},
        PENDING: {APPROVED, REJECTED, NEEDS_REVISION, WITHDRAWN},
        NEEDS_REVISION: {PROCESSING, PENDING},
        APPROVED: {PENDING, NEEDS_REVISION, WITHDRAWN},
        REJECTED: set(),
        WITHDRAWN: set(),
    }


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class InvalidTransition(ValueError):
    pass


LANGUAGES = [
    ("garhwali", "Garhwali"),
    ("kumaoni", "Kumaoni"),
    ("jaunsari", "Jaunsari"),
    ("hindi", "Hindi"),
    ("english", "English"),
    ("other", "Other"),
]
LANGUAGE_LABELS = dict(LANGUAGES)

UTTARAKHAND_DISTRICTS = [
    "Almora", "Bageshwar", "Chamoli", "Champawat", "Dehradun", "Haridwar",
    "Nainital", "Pauri Garhwal", "Pithoragarh", "Rudraprayag",
    "Tehri Garhwal", "Udham Singh Nagar", "Uttarkashi",
]

DEFAULT_CATEGORIES = [
    ("folk-stories", "Folk Stories", "Legends, fables and traditional narratives."),
    ("folk-songs", "Folk Songs", "Jagar, Basanti, Mangal, Jhumeilo, Chhopati and other songs."),
    ("recipes", "Recipes & Food", "Traditional recipes and local food knowledge."),
    ("dialects", "Dialects & Language", "Words, phrases and speech of Garhwali, Kumaoni and related languages."),
    ("traditions", "Festivals & Traditions", "Festivals, customs, rituals and cultural practices."),
    ("oral-histories", "Oral Histories", "Life stories and village memories shared by elders."),
]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), nullable=False, unique=True)
    email = db.Column(db.String(254), nullable=False, unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    bio = db.Column(db.String(500))
    role = db.Column(db.String(20), nullable=False, default=Role.PUBLIC, index=True)
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_login_at = db.Column(db.DateTime)

    records = db.relationship("KnowledgeRecord", back_populates="owner", foreign_keys="KnowledgeRecord.owner_id")

    __table_args__ = (
        CheckConstraint("role in ('public_user','contributor','steward','admin')", name="ck_user_role"),
    )

    @validates("email")
    def _norm_email(self, _key, value):
        value = (value or "").strip().lower()
        if "@" not in value:
            raise ValueError("Invalid email address")
        return value

    @validates("username")
    def _norm_username(self, _key, value):
        value = (value or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", value):
            raise ValueError("Username must be 3-40 letters, numbers, dot, dash or underscore")
        return value

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):  # Flask-Login
        return self.is_active_account

    @property
    def role_label(self):
        return Role.LABELS.get(self.role, self.role)

    @property
    def can_contribute(self):
        return self.role in Role.CAN_CONTRIBUTE

    @property
    def can_review(self):
        return self.role in Role.CAN_REVIEW

    @property
    def is_admin(self):
        return self.role == Role.ADMIN


@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    return user if user and user.is_active_account else None


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(60), nullable=False, unique=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    description = db.Column(db.String(300))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    records = db.relationship("KnowledgeRecord", back_populates="category")


# ---------------------------------------------------------------------------
# Knowledge records
# ---------------------------------------------------------------------------
class KnowledgeRecord(db.Model):
    __tablename__ = "knowledge_records"
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    content_type = db.Column(db.String(10), nullable=False, default="text")  # text|audio|video
    body_text = db.Column(db.Text)  # written story / contributor text
    language = db.Column(db.String(20), nullable=False, default="hindi")
    district = db.Column(db.String(40), index=True)
    village = db.Column(db.String(100))
    tags = db.Column(db.String(400), default="")  # comma separated, lower-case

    # AI suggestions (kept separate from contributor-confirmed values)
    summary = db.Column(db.Text)
    ai_suggested_tags = db.Column(db.String(400))
    ai_metadata_json = db.Column(db.Text)

    # consent & publication
    attribution = db.Column(db.String(12), nullable=False, default="named")  # named|anonymous|community
    consent_given = db.Column(db.Boolean, nullable=False, default=False)
    consent_at = db.Column(db.DateTime)
    is_public = db.Column(db.Boolean, nullable=False, default=False)  # publication preference

    status = db.Column(db.String(20), nullable=False, default=Status.DRAFT, index=True)
    steward_note = db.Column(db.Text)  # latest note shown to contributor
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    submitted_at = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)
    withdrawn_at = db.Column(db.DateTime)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    owner = db.relationship("User", back_populates="records", foreign_keys=[owner_id])
    verified_by = db.relationship("User", foreign_keys=[verified_by_id])
    category = db.relationship("Category", back_populates="records")
    media = db.relationship("MediaAsset", back_populates="record", cascade="all, delete-orphan")
    transcript = db.relationship("Transcript", back_populates="record", uselist=False, cascade="all, delete-orphan")
    translations = db.relationship("Translation", back_populates="record", cascade="all, delete-orphan")
    jobs = db.relationship("ProcessingJob", back_populates="record", cascade="all, delete-orphan",
                           order_by="ProcessingJob.id.desc()")
    reviews = db.relationship("Review", back_populates="record", cascade="all, delete-orphan",
                              order_by="Review.id.desc()")
    vector_refs = db.relationship("VectorRef", back_populates="record", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status in ('draft','processing','pending_review','needs_revision','approved','rejected','withdrawn')",
                        name="ck_record_status"),
        CheckConstraint("content_type in ('text','audio','video')", name="ck_record_content_type"),
        CheckConstraint("attribution in ('named','anonymous','community')", name="ck_record_attribution"),
        Index("ix_record_public_lookup", "status", "is_public", "consent_given"),
    )

    @validates("title")
    def _title(self, _k, v):
        v = (v or "").strip()
        if not 3 <= len(v) <= 200:
            raise ValueError("Title must be between 3 and 200 characters")
        return v

    @validates("tags")
    def _tags(self, _k, v):
        return normalise_tags(v)

    # -- state machine ----------------------------------------------------
    def can_transition(self, new_status: str) -> bool:
        return new_status in Status.TRANSITIONS.get(self.status, set())

    def transition(self, new_status: str) -> None:
        if not self.can_transition(new_status):
            raise InvalidTransition(f"Cannot move a record from '{self.status}' to '{new_status}'.")
        self.status = new_status

    # -- visibility ---------------------------------------------------------
    @property
    def is_publicly_visible(self) -> bool:
        return (self.status == Status.APPROVED and bool(self.is_public)
                and bool(self.consent_given) and self.withdrawn_at is None)

    @classmethod
    def public_query(cls):
        return cls.query.filter(cls.status == Status.APPROVED, cls.is_public.is_(True),
                                cls.consent_given.is_(True), cls.withdrawn_at.is_(None))

    # -- helpers ----------------------------------------------------------------
    @property
    def status_label(self):
        return Status.LABELS.get(self.status, self.status)

    @property
    def language_label(self):
        return LANGUAGE_LABELS.get(self.language, self.language)

    @property
    def tag_list(self):
        return [t for t in (self.tags or "").split(",") if t]

    @property
    def primary_media(self):
        for m in self.media:
            if m.kind in ("audio", "video"):
                return m
        return None

    @property
    def transcript_text(self) -> str:
        t = self.transcript
        if not t:
            return ""
        return (t.edited_text if t.edited_text is not None else t.original_text) or ""

    def translation_for(self, lang: str):
        for t in self.translations:
            if t.target_language == lang:
                return t
        return None

    @property
    def attribution_label(self) -> str:
        if self.attribution == "named":
            return self.owner.display_name
        if self.attribution == "community":
            return "Community contribution"
        return "Anonymous contributor"

    @property
    def ai_metadata(self) -> dict:
        try:
            return json.loads(self.ai_metadata_json) if self.ai_metadata_json else {}
        except ValueError:
            return {}

    def searchable_text(self) -> str:
        """All text of this record that may be embedded / retrieved."""
        parts = [self.title, self.description or "", self.body_text or "", self.transcript_text, self.summary or ""]
        for t in self.translations:
            if t.text:
                parts.append(t.text)
        return "\n\n".join(p.strip() for p in parts if p and p.strip())


def normalise_tags(value) -> str:
    if isinstance(value, (list, tuple)):
        value = ",".join(value)
    seen, out = set(), []
    for raw in re.split(r"[,\n;]", value or ""):
        tag = re.sub(r"\s+", " ", raw.strip().lower())[:40]
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return ",".join(out[:15])


class MediaAsset(db.Model):
    __tablename__ = "media_assets"
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("knowledge_records.id"), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False)  # audio|video|photo|document
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(120), nullable=False, unique=True)
    mime_type = db.Column(db.String(100), nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    record = db.relationship("KnowledgeRecord", back_populates="media")

    __table_args__ = (CheckConstraint("kind in ('audio','video','photo','document')", name="ck_media_kind"),)


class Transcript(db.Model):
    __tablename__ = "transcripts"
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("knowledge_records.id"), nullable=False, unique=True)
    original_text = db.Column(db.Text, nullable=False, default="")  # preserved exactly as produced / first entered
    edited_text = db.Column(db.Text)  # human-corrected version
    detected_language = db.Column(db.String(20))
    source = db.Column(db.String(30), nullable=False, default="manual")  # faster_whisper|openai|manual
    model_name = db.Column(db.String(80))
    edited_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    record = db.relationship("KnowledgeRecord", back_populates="transcript")


class Translation(db.Model):
    __tablename__ = "translations"
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("knowledge_records.id"), nullable=False, index=True)
    target_language = db.Column(db.String(5), nullable=False)  # hi | en
    text = db.Column(db.Text, nullable=False, default="")
    machine_text = db.Column(db.Text)  # original machine output, preserved
    provider = db.Column(db.String(30), nullable=False, default="manual")
    is_human_edited = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    record = db.relationship("KnowledgeRecord", back_populates="translations")

    __table_args__ = (
        UniqueConstraint("record_id", "target_language", name="uq_translation_record_lang"),
        CheckConstraint("target_language in ('hi','en')", name="ck_translation_lang"),
    )


class ProcessingJob(db.Model):
    __tablename__ = "processing_jobs"
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("knowledge_records.id"), nullable=False, index=True)
    status = db.Column(db.String(12), nullable=False, default=JobStatus.QUEUED, index=True)
    stage = db.Column(db.String(30), nullable=False, default="queued")
    progress = db.Column(db.Integer, nullable=False, default=0)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    error_code = db.Column(db.String(40))
    error_message = db.Column(db.Text)
    warnings = db.Column(db.Text)  # newline separated, e.g. skipped steps
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)

    record = db.relationship("KnowledgeRecord", back_populates="jobs")

    __table_args__ = (
        CheckConstraint("status in ('queued','running','succeeded','failed')", name="ck_job_status"),
        CheckConstraint("progress >= 0 and progress <= 100", name="ck_job_progress"),
    )


class Review(db.Model):
    __tablename__ = "reviews"
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("knowledge_records.id"), nullable=False, index=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    decision = db.Column(db.String(20), nullable=False)  # approved|rejected|needs_revision|comment
    from_status = db.Column(db.String(20), nullable=False)
    to_status = db.Column(db.String(20), nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    record = db.relationship("KnowledgeRecord", back_populates="reviews")
    reviewer = db.relationship("User")

    __table_args__ = (
        CheckConstraint("decision in ('approved','rejected','needs_revision','comment')", name="ck_review_decision"),
    )


class VectorRef(db.Model):
    """Maps DB records to ids in the vector index (embeddings live only in ChromaDB)."""
    __tablename__ = "vector_refs"
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("knowledge_records.id"), nullable=False, index=True)
    vector_id = db.Column(db.String(60), nullable=False, unique=True)
    chunk_index = db.Column(db.Integer, nullable=False)
    embedding_model = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    record = db.relationship("KnowledgeRecord", back_populates="vector_refs")


class ChatSession(db.Model):
    __tablename__ = "chat_sessions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    anon_key = db.Column(db.String(64), index=True)
    title = db.Column(db.String(120), nullable=False, default="New conversation")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    messages = db.relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                               order_by="ChatMessage.id")


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = db.Column(db.String(10), nullable=False)  # user|assistant
    content = db.Column(db.Text, nullable=False)
    mode = db.Column(db.String(20))  # ai_answer|retrieval_only|no_evidence|llm_error
    sources_json = db.Column(db.Text)
    source_record_ids = db.Column(db.String(400))  # ",5,7," for redaction lookups
    redacted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    session = db.relationship("ChatSession", back_populates="messages")

    __table_args__ = (CheckConstraint("role in ('user','assistant')", name="ck_chat_role"),)

    @property
    def sources(self):
        try:
            return json.loads(self.sources_json) if self.sources_json else []
        except ValueError:
            return []


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    action = db.Column(db.String(60), nullable=False, index=True)
    target_type = db.Column(db.String(30))
    target_id = db.Column(db.Integer)
    detail = db.Column(db.String(500))
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    actor = db.relationship("User")


class ContactMessage(db.Model):
    __tablename__ = "contact_messages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    subject = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_resolved = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


def audit(action: str, actor=None, target_type=None, target_id=None, detail=None, commit=False):
    """Append an audit-log entry (does not commit unless asked)."""
    from flask import has_request_context, request
    ip = request.remote_addr if has_request_context() else None
    entry = AuditLog(actor_id=getattr(actor, "id", None), action=action, target_type=target_type,
                     target_id=target_id, detail=(detail or "")[:500] or None, ip_address=ip)
    db.session.add(entry)
    if commit:
        db.session.commit()
    return entry
