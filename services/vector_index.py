"""
Access-aware semantic search.

CRITICAL RULE: permission filtering happens in the SQL query, BEFORE any
record's embedding is compared to the query. A restricted record's vector
never even enters the similarity computation for a user who isn't allowed
to see it - so it cannot leak through search or RAG.
"""
import json

from services.ai_pipeline import embed_text, cosine_similarity


def _allowed_records_query(user):
    """Returns (sql, params) selecting only knowledge_records this user may see.
    Applied BEFORE vector search, never after."""
    base = """
        SELECT kr.*, d.name AS district_name, c.name AS category_name
        FROM knowledge_records kr
        LEFT JOIN districts d ON d.id = kr.district_id
        LEFT JOIN categories c ON c.id = kr.category_id
        WHERE kr.status = 'community_verified'
          AND kr.embedding IS NOT NULL
    """
    if user and user["role"] in ("steward", "admin"):
        return base, ()  # stewards/admins can search everything verified
    if user and user["community"]:
        return (
            base + " AND (kr.access_level = 'public' OR kr.community = ?)",
            (user["community"],),
        )
    return base + " AND kr.access_level = 'public'", ()


def search(db, user, query_text, top_k=5, district_id=None, category_id=None):
    sql, params = _allowed_records_query(user)
    params = list(params)
    if district_id:
        sql += " AND kr.district_id = ?"
        params.append(district_id)
    if category_id:
        sql += " AND kr.category_id = ?"
        params.append(category_id)

    rows = db.execute(sql, params).fetchall()
    if not rows:
        return []

    query_vec = embed_text(query_text)
    scored = []
    for row in rows:
        try:
            record_vec = json.loads(row["embedding"])
        except (TypeError, ValueError):
            continue
        score = cosine_similarity(query_vec, record_vec)
        scored.append((score, row))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in scored[:top_k]]
