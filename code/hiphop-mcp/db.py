"""SQLite schema and connection helpers."""
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / "openclaw-tools" / "data" / "spotify.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    artists TEXT NOT NULL,
    album TEXT,
    duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT NOT NULL,
    played_at TEXT NOT NULL UNIQUE,
    FOREIGN KEY (track_id) REFERENCES tracks(id)
);

CREATE INDEX IF NOT EXISTS idx_plays_played_at ON plays(played_at);
CREATE INDEX IF NOT EXISTS idx_plays_track ON plays(track_id);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


if __name__ == "__main__":
    with connect() as c:
        print("Initialized", DB_PATH)
        print(c.execute("SELECT COUNT(*) FROM plays").fetchone()[0], "plays")
        print(c.execute("SELECT COUNT(*) FROM tracks").fetchone()[0], "tracks")
