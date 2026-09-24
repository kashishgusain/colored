# LOKVAANI AI

Preserve the past. Understand it. Build the future.

A working prototype for preserving Uttarakhand's traditional/oral knowledge: a knowledge
holder uploads a short video or audio recording, AI transcribes and translates it, structures
it into a searchable knowledge record, a Community Steward verifies it, and anyone with
permission can find it through semantic search or by asking **Ask LOKVAANI AI** directly.

Built and smoke-tested end to end in this environment (Flask dev server, curl) — see
**Verified working** below for exactly what was checked.

## Quick start

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # add your free Groq API key here, or leave blank for demo mode
python seed_data.py             # loads districts, categories, demo accounts, sample records
python app.py
```

Open http://127.0.0.1:5000

Demo accounts (created by `seed_data.py`):

| Username | Password    | Role    | Community                    |
|----------|-------------|---------|-------------------------------|
| admin    | admin123    | admin   | —                             |
| steward  | steward123  | steward | —                             |
| holder   | holder123   | user    | Bhotiya Weavers Collective    |

## Real AI vs. demo mode

If `GROQ_API_KEY` in `.env` is blank, the app runs in **demo mode**: every AI stage still
executes and every UI state still works, but transcription/translation/extraction output is
clearly labeled as demo/fallback instead of pretending to be a live result. Get a free key at
https://console.groq.com and set it to enable real transcription (`whisper-large-v3`) and real
translation/extraction/RAG answers (Llama via Groq's chat API).

Video uploads (`.mp4/.mov/.webm`) need `ffmpeg` on your `PATH` to extract audio. Audio files
(`.mp3/.wav/.m4a`) are sent to the transcription API directly.

Semantic search and the Ask LOKVAANI AI embeddings use a small dependency-free local hashing
vectorizer (`services/ai_pipeline.py::embed_text`) — it works out of the box with no downloads
or API key. Swap in `sentence-transformers` there later for stronger quality if you have
bandwidth to spare.

## Verified working (tested in this build)

- Server boots, all core routes return 200 (home, explore, search, ask, risk dashboard, login)
- `seed_data.py` populates 13 districts, 14 categories, 3 demo accounts, 4 sample knowledge
  records with real computed embeddings, 5 risk assessments
- **Access-aware RAG, confirmed end to end**: anonymous users and a logged-in user without a
  matching community only retrieve the 3 *public* seeded records through both `/search` and
  `/ask`. The one *community-only* record (wool weaving, community "Bhotiya Weavers
  Collective") is retrieved **only** once logged in as the `holder` account, whose community
  matches. It is filtered out in SQL before the vector search ever runs — never fetched and
  hidden, never leaked in search/RAG for anyone else.
- Knowledge Risk Dashboard renders real computed scores with transparent per-factor breakdowns
  (e.g. Wooden Water-Mill scored Critical · 91.2/100, Wool Weaving Critical · 87.5/100, using
  the seeded practitioner/documentation/transmission inputs)
- Steward account can reach the review/approve screen and sees steward-only controls; a
  regular user does not
- Zero server-side exceptions across the tested flows

## Not yet exercised

- The live upload → ffmpeg → Groq Whisper → Groq LLM extraction path was written and
  demo-mode-tested (falls back correctly with no API key), but not run against a real Groq key
  in this environment (no network access here). Test this with your own key before the demo.
- Product/marketplace, researcher access-request workflow, and full community-membership
  approval flow are intentionally out of scope for this build (see the original 10-hour scope
  doc) — `community` is currently just a free-text field set at registration.

## Project structure

```
app.py                 Flask app factory, root routes
config.py               Environment-driven configuration
database.py              SQLite schema + connection helpers
utils.py                 Auth decorators, Knowledge ID generation
seed_data.py              One-time seed script (districts, demo users, sample records)
services/
  ai_pipeline.py           Transcription, translation+extraction, local embeddings (Groq + demo fallback)
  vector_index.py           Access-aware semantic search (permission filter BEFORE retrieval)
  risk.py                    Knowledge Risk Detector scoring
routes/
  auth.py, upload.py, knowledge.py, search.py, dashboard.py
templates/                Jinja2 templates (editorial design system in static/css/style.css)
static/                    CSS + JS (status polling, nav, transcript tabs)
uploads/                   Uploaded media (gitignored; served only to authenticated owners)
```

## Known simplifications (by design, for a 10-hour build)

- Async processing is a plain background thread per upload, not a job queue — fine at demo
  scale, not for production concurrency.
- Community membership is self-declared free text at registration, not steward-approved.
- No computer-vision safety screening on video frames; only text-based moderation via the
  extraction LLM prompt.
- Reporting/flagging workflow, product/marketplace layer, and researcher access-request flow
  are not built — see the original scope doc for what was deliberately cut.
