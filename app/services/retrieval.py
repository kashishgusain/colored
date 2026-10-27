"""Keyword + semantic retrieval, and the vector-index synchronisation rules.

Security model: a record may exist in the vector index ONLY while it is approved, public and
consented. `sync_record` is the single function that enforces this and is called after every
change. Every search result is additionally re-checked against the database (defence in depth).
"""
import re
from dataclasses import dataclass

from flask import current_app
from sqlalchemy import or_

from ..extensions import db
from ..models import ChatMessage, KnowledgeRecord, Transcript, Translation, VectorRef
from .embeddings import TOKEN_RE, get_embedder
from .errors import ServiceError

COLLECTION = "lokvaani_records"
CHUNK_CHARS = 900
CHUNK_OVERLAP = 120
STOPWORDS = set("""a an the and or of to in on at for from with about is are was were be been what which who whom how
why when where do does did tell me us please summarize summarise describe explain any this that these those it its
as by into than then there their they them you your i my we our can could would should has have had not no yes
archive records record archived mention mentioned say says said ka ki ke hai hain me se ko aur kya""".split())


@dataclass
class Passage:
    record: KnowledgeRecord
    text: str
    score: float
    source: str  # "semantic" | "keyword"


# --------------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------------
def tokenize(query: str) -> list[str]:
    toks = [t.lower() for t in TOKEN_RE.findall(query or "")]
    keep = [t for t in toks if t not in STOPWORDS and len(t) > 1]
    return list(dict.fromkeys(keep or [t for t in toks if len(t) > 1]))[:10]


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks, buf = [], ""
    for para in paras:
        while len(para) > size:  # hard-split very long paragraphs on sentence/space boundaries
            cut = max(para.rfind("। ", 0, size), para.rfind(". ", 0, size), para.rfind(" ", 0, size))
            cut = cut + 1 if cut > size // 2 else size
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.append(para[:cut].strip())
            para = para[max(cut - overlap, 1):].strip() if len(para) - cut > overlap else para[cut:].strip()
            if len(para) <= overlap:
                para = ""
        if buf and len(buf) + len(para) + 2 > size:
            chunks.append(buf)
            buf = ""
        buf = f"{buf}\n\n{para}".strip() if para else buf
    if buf:
        chunks.append(buf)
    return [c for c in chunks if c.strip()]


def _like(token: str) -> str:
    return "%" + token.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"


def _token_clause(token: str):
    pat = _like(token)
    r = KnowledgeRecord
    return or_(
        r.title.ilike(pat, escape="\\"), r.description.ilike(pat, escape="\\"), r.tags.ilike(pat, escape="\\"),
        r.village.ilike(pat, escape="\\"), r.body_text.ilike(pat, escape="\\"), r.summary.ilike(pat, escape="\\"),
        r.transcript.has(or_(Transcript.original_text.ilike(pat, escape="\\"),
                             Transcript.edited_text.ilike(pat, escape="\\"))),
        r.translations.any(Translation.text.ilike(pat, escape="\\")),
    )


def apply_filters(query, filters: dict):
    f = filters or {}
    r = KnowledgeRecord
    if f.get("category_id"):
        query = query.filter(r.category_id == f["category_id"])
    if f.get("language"):
        query = query.filter(r.language == f["language"])
    if f.get("district"):
        query = query.filter(r.district == f["district"])
    if f.get("content_type") == "text":
        query = query.filter(r.content_type == "text")
    elif f.get("content_type") == "media":
        query = query.filter(r.content_type.in_(("audio", "video")))
    elif f.get("content_type") in ("audio", "video"):
        query = query.filter(r.content_type == f["content_type"])
    return query


# --------------------------------------------------------------------------------
# Vector index (ChromaDB)
# --------------------------------------------------------------------------------
def _collection():
    import chromadb

    client = chromadb.PersistentClient(path=str(current_app.config["VECTOR_DIR"]))
    return client.get_or_create_collection(COLLECTION, embedding_function=None,
                                           metadata={"hnsw:space": "cosine"})


def vector_available() -> tuple[bool, str]:
    try:
        embedder = get_embedder()
        if current_app.config["EMBEDDING_PROVIDER"] == "sentence_transformers":
            import sentence_transformers  # noqa: F401
        _collection()
        return True, f"Embedding model: {embedder.name}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def remove_record(record_id: int) -> None:
    """Remove every vector belonging to the record (index + VectorRef rows)."""
    refs = VectorRef.query.filter_by(record_id=record_id).all()
    ids = [r.vector_id for r in refs]
    try:
        col = _collection()
        if ids:
            col.delete(ids=ids)
        else:
            col.delete(where={"record_id": record_id})
    except Exception as exc:  # index unavailable: keep refs so a later reindex can clean up
        current_app.logger.warning("Vector removal failed for record %s: %s", record_id, exc)
        return
    for ref in refs:
        db.session.delete(ref)


def index_record(record: KnowledgeRecord) -> int:
    """Embed and store a (public) record. Replaces any previous vectors."""
    remove_record(record.id)
    chunks = chunk_text(record.searchable_text())
    if not chunks:
        return 0
    embedder = get_embedder()
    vectors = embedder.encode(chunks)
    ids = [f"rec{record.id}-c{i}" for i in range(len(chunks))]
    metas = [{"record_id": record.id, "chunk_index": i, "is_public": True} for i in range(len(chunks))]
    _collection().upsert(ids=ids, embeddings=vectors, documents=chunks, metadatas=metas)
    for i, vid in enumerate(ids):
        db.session.add(VectorRef(record_id=record.id, vector_id=vid, chunk_index=i, embedding_model=embedder.name))
    return len(chunks)


def redact_chats_for_record(record_id: int) -> None:
    """Chat answers that cited a record must not outlive its public status."""
    msgs = ChatMessage.query.filter(ChatMessage.source_record_ids.like(f"%,{int(record_id)},%"),
                                    ChatMessage.redacted.is_(False)).all()
    for m in msgs:
        m.content = "[This answer cited a record that is no longer public, so it was removed.]"
        m.sources_json = None
        m.source_record_ids = None
        m.redacted = True


def sync_record(record: KnowledgeRecord) -> str:
    """Make the vector index agree with the record's current visibility. Returns an outcome label."""
    if record.is_publicly_visible:
        try:
            n = index_record(record)
            return f"indexed:{n}"
        except Exception as exc:
            current_app.logger.warning("Indexing failed for record %s: %s", record.id, exc)
            return f"index_failed:{type(exc).__name__}"
    remove_record(record.id)
    redact_chats_for_record(record.id)
    return "removed"


def reindex_all() -> dict:
    """Rebuild the index from the database. Drops anything not currently public."""
    try:
        col = _collection()
        existing = col.get(include=[])["ids"]
        if existing:
            col.delete(ids=existing)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    VectorRef.query.delete()
    indexed = 0
    for rec in KnowledgeRecord.public_query().all():
        indexed += 1 if index_record(rec) else 0
    db.session.commit()
    return {"ok": True, "records_indexed": indexed}


def index_health() -> dict:
    ok, detail = vector_available()
    info = {"available": ok, "detail": detail, "vectors": None, "public_records": KnowledgeRecord.public_query().count(),
            "indexed_records": db.session.query(VectorRef.record_id).distinct().count(), "in_sync": None}
    if ok:
        try:
            info["vectors"] = _collection().count()
            info["in_sync"] = info["indexed_records"] == info["public_records"] and info["vectors"] == VectorRef.query.count()
        except Exception as exc:
            info["available"], info["detail"] = False, str(exc)
    return info


# --------------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------------
def keyword_search(query: str, filters: dict | None = None, page: int = 1, per_page: int = 9):
    q = apply_filters(KnowledgeRecord.public_query(), filters or {})
    for tok in tokenize(query):
        q = q.filter(_token_clause(tok))
    return q.order_by(KnowledgeRecord.approved_at.desc().nullslast(), KnowledgeRecord.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False)


def semantic_candidates(query: str, k: int = 20, filters: dict | None = None):
    """Return [(record_id, chunk_text, similarity)] from ChromaDB; raises if unavailable."""
    embedder = get_embedder()
    vec = embedder.encode([query])[0]
    col = _collection()
    if col.count() == 0:
        return []
    res = col.query(query_embeddings=[vec], n_results=min(k, col.count()), where={"is_public": True},
                    include=["documents", "metadatas", "distances"])
    out = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        out.append((int(meta["record_id"]), doc, 1.0 - float(dist)))
    return out


def search_records(query: str, filters: dict | None = None, page: int = 1, per_page: int = 9) -> dict:
    """Public search page. Semantic results first (when available), keyword as fallback/extension."""
    filters = filters or {}
    query = (query or "").strip()
    if not query:
        pag = keyword_search("", filters, page, per_page)
        return {"records": pag.items, "pagination": pag, "mode": "browse", "note": None}

    semantic_ids, note = [], None
    try:
        hits = semantic_candidates(query, k=30)
        seen = {}
        for rid, _doc, sim in hits:
            seen[rid] = max(seen.get(rid, 0.0), sim)
        ranked = [rid for rid, sim in sorted(seen.items(), key=lambda kv: -kv[1]) if sim > 0.25]
        if ranked:
            q = apply_filters(KnowledgeRecord.public_query(), filters).filter(KnowledgeRecord.id.in_(ranked))
            by_id = {r.id: r for r in q.all()}  # DB re-check: only still-public records survive
            semantic_ids = [rid for rid in ranked if rid in by_id]
    except Exception as exc:
        note = "Semantic search is unavailable right now, so keyword search was used."
        current_app.logger.info("Semantic search unavailable: %s", exc)

    kw_pag = keyword_search(query, filters, 1, 200)
    kw_ids = [r.id for r in kw_pag.items]
    ordered = list(dict.fromkeys(semantic_ids + kw_ids))
    total = len(ordered)
    start, end = (page - 1) * per_page, page * per_page
    page_ids = ordered[start:end]
    by_id = {r.id: r for r in KnowledgeRecord.query.filter(KnowledgeRecord.id.in_(page_ids)).all()}
    records = [by_id[i] for i in page_ids if i in by_id]
    pages = max(1, -(-total // per_page))
    mode = "semantic+keyword" if semantic_ids else "keyword"
    return {"records": records, "mode": mode, "note": note,
            "pagination": _SimplePagination(page, per_page, total, pages)}


class _SimplePagination:
    def __init__(self, page, per_page, total, pages):
        self.page, self.per_page, self.total, self.pages = page, per_page, total, pages
        self.has_prev, self.has_next = page > 1, page < pages
        self.prev_num, self.next_num = page - 1, page + 1

    def iter_pages(self, **_kw):
        return range(1, self.pages + 1)


def related_records(record: KnowledgeRecord, limit: int = 3) -> list[KnowledgeRecord]:
    q = KnowledgeRecord.public_query().filter(KnowledgeRecord.id != record.id)
    tags = record.tag_list
    clauses = [KnowledgeRecord.category_id == record.category_id]
    clauses += [KnowledgeRecord.tags.ilike(_like(t), escape="\\") for t in tags[:5]]
    return q.filter(or_(*clauses)).order_by(KnowledgeRecord.approved_at.desc().nullslast()).limit(limit).all()


# --------------------------------------------------------------------------------
# Passages for RAG
# --------------------------------------------------------------------------------
def retrieve_passages(question: str, k: int = 5) -> tuple[list[Passage], str | None]:
    """Return the best evidence passages from public records only (+ an optional note)."""
    passages: dict[tuple[int, int], Passage] = {}
    note = None
    try:
        for rid, doc, sim in semantic_candidates(question, k=15):
            if sim > 0.25:
                passages[(rid, hash(doc))] = Passage(None, doc, sim, "semantic")  # record filled below
    except Exception as exc:
        note = "Semantic index unavailable; used keyword matching."
        current_app.logger.info("RAG semantic retrieval unavailable: %s", exc)
        passages.clear()

    # re-validate against the DB: unauthorised/obsolete vectors are dropped here
    sem_ids = {rid for (rid, _h) in passages}
    visible = {r.id: r for r in KnowledgeRecord.public_query().filter(KnowledgeRecord.id.in_(sem_ids)).all()} if sem_ids else {}
    result = []
    for (rid, _h), p in passages.items():
        if rid in visible:
            p.record = visible[rid]
            result.append(p)

    # keyword retrieval (ANY token) scored in Python over the public candidates
    toks = tokenize(question)
    if toks:
        cands = (KnowledgeRecord.public_query().filter(or_(*[_token_clause(t) for t in toks]))
                 .limit(40).all())
        for rec in cands:
            best = None
            title_l = rec.title.lower()
            for ch in chunk_text(rec.searchable_text()):
                low = ch.lower()
                hits = sum(1 for t in toks if t in low)
                if hits:
                    score = hits / len(toks) + (0.15 if any(t in title_l for t in toks) else 0)
                    if not best or score > best[0]:
                        best = (score, ch)
            if best:
                result.append(Passage(rec, best[1], min(best[0], 0.99), "keyword"))

    # best passage per record, then top k
    per_record: dict[int, Passage] = {}
    for p in sorted(result, key=lambda x: -x.score):
        per_record.setdefault(p.record.id, p)
    final = sorted(per_record.values(), key=lambda x: -x.score)[:k]
    return final, note
