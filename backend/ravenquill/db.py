"""SQLite storage. The database *is* the living document: every paragraph keeps
its original text and its current (edited) text, plus a history of edits."""
import json
import sqlite3
from contextlib import contextmanager

from .config import DATA_DIR, DB_PATH, DEFAULT_SETTINGS, PROJECTS_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    source_filename TEXT,
    intensity TEXT NOT NULL DEFAULT 'standard',
    voice_profile TEXT NOT NULL DEFAULT '',
    style_sheet TEXT NOT NULL DEFAULT '',
    report TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    title TEXT NOT NULL,
    notes TEXT  -- Story Architect notes; NULL until read
);

CREATE TABLE IF NOT EXISTS paragraphs (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,              -- position in the whole book
    kind TEXT NOT NULL,                -- 'heading' | 'body' | 'scene_break'
    original TEXT NOT NULL,
    current TEXT NOT NULL,
    done_stages TEXT NOT NULL DEFAULT ',',   -- e.g. ',prose,copyedit,'
    edited_by TEXT NOT NULL DEFAULT ',',     -- stages that changed the text
    flagged INTEGER NOT NULL DEFAULT 0,      -- has a rejected suggestion to look at
    reviewed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_par_chapter ON paragraphs(chapter_id, idx);
CREATE INDEX IF NOT EXISTS ix_par_project ON paragraphs(project_id, idx);

CREATE TABLE IF NOT EXISTS edits (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    paragraph_id INTEGER NOT NULL REFERENCES paragraphs(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,               -- persona name, or 'author'
    before TEXT NOT NULL,
    after TEXT NOT NULL,
    status TEXT NOT NULL,              -- 'applied' | 'rejected'
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_edits_par ON edits(paragraph_id);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    stages TEXT NOT NULL,              -- JSON list
    status TEXT NOT NULL,              -- queued|running|paused|done|error|cancelled
    current_stage TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    error TEXT,
    llm_seconds REAL NOT NULL DEFAULT 0,
    llm_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    data TEXT NOT NULL,                -- JSON {paragraph_id: current_text}
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, label)
);

-- Outlines are checked by the Outline Doctor in rounds until no holes are left open.
CREATE TABLE IF NOT EXISTS outlines (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'idle',   -- idle|reviewing|error
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outline_rounds (
    id INTEGER PRIMARY KEY,
    outline_id INTEGER NOT NULL REFERENCES outlines(id) ON DELETE CASCADE,
    round INTEGER NOT NULL,
    text TEXT NOT NULL,                -- the outline as it was reviewed
    new_holes INTEGER NOT NULL DEFAULT 0,
    fixed_holes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outline_holes (
    id INTEGER PRIMARY KEY,
    outline_id INTEGER NOT NULL REFERENCES outlines(id) ON DELETE CASCADE,
    round INTEGER NOT NULL,            -- round that raised it
    title TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'major',  -- major|minor
    detail TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',     -- open|fixed|rejected|explained
    response TEXT NOT NULL DEFAULT '',       -- author's reason or explanation
    resolved_round INTEGER,            -- round the Outline Doctor confirmed the fix
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_holes_outline ON outline_holes(outline_id);
"""


def init():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(SCHEMA)
        # A server restart interrupts any running job; let the user resume it.
        db.execute("UPDATE jobs SET status='paused', message='Interrupted (server restarted). Press Resume.' "
                   "WHERE status IN ('running','queued')")
        db.execute("UPDATE outlines SET status='error', error='Interrupted (server restarted). Check again.' "
                   "WHERE status='reviewing'")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def get_settings() -> dict:
    with connect() as db:
        stored = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT key, value FROM settings")}
    return {**DEFAULT_SETTINGS, **{k: v for k, v in stored.items() if k in DEFAULT_SETTINGS}}


def save_settings(values: dict) -> dict:
    with connect() as db:
        for key, value in values.items():
            if key in DEFAULT_SETTINGS:
                db.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                           "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
    return get_settings()


def project_dir(project_id: int):
    path = PROJECTS_DIR / str(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
