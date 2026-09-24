import sqlite3
from flask import g, current_app

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',          -- user, steward, admin
    community TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS districts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    slug TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_id TEXT UNIQUE NOT NULL,
    title TEXT,
    district_id INTEGER,
    category_id INTEGER,
    community TEXT,
    language TEXT,
    original_transcript TEXT,
    translation_en TEXT,
    materials TEXT,               -- JSON array
    tools TEXT,                   -- JSON array
    steps TEXT,                   -- JSON array
    cultural_significance TEXT,
    historical_context TEXT,
    summary TEXT,
    keywords TEXT,                -- JSON array
    status TEXT NOT NULL DEFAULT 'processing',   -- processing, ai_extracted, community_verified, failed
    access_level TEXT NOT NULL DEFAULT 'public', -- public, community_only
    contributor_id INTEGER,
    media_path TEXT,
    embedding TEXT,                -- JSON array of floats
    is_demo_ai INTEGER DEFAULT 0,   -- 1 if AI stage ran in demo/fallback mode
    is_seed INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (district_id) REFERENCES districts(id),
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (contributor_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS risk_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    practice_title TEXT NOT NULL,
    district_id INTEGER,
    category_id INTEGER,
    practitioners INTEGER,
    young_practitioners INTEGER,
    documentation_level INTEGER,       -- 1-5 (5 = well documented)
    frequency_trend INTEGER,           -- 1-5 (5 = frequent / stable)
    geographic_concentration INTEGER,  -- 1-5 (5 = highly concentrated)
    transmission_level INTEGER,        -- 1-5 (5 = strong transmission to youth)
    score REAL,
    band TEXT,
    notes TEXT,
    FOREIGN KEY (district_id) REFERENCES districts(id),
    FOREIGN KEY (category_id) REFERENCES categories(id)
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        db.commit()


def register_db(app):
    app.teardown_appcontext(close_db)
