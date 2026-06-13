import sqlite3
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
  path TEXT PRIMARY KEY,
  notion_page_id TEXT NOT NULL,
  content_hash TEXT,
  is_folder INTEGER NOT NULL,
  last_synced TEXT
);
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def get_page(path: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM pages WHERE path = ?", (path,)).fetchone()
        return dict(row) if row else None


def upsert_page(path: str, notion_page_id: str, content_hash: str | None, is_folder: bool, last_synced: str):
    with connect() as c:
        c.execute(
            """
            INSERT INTO pages (path, notion_page_id, content_hash, is_folder, last_synced)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              notion_page_id = excluded.notion_page_id,
              content_hash = excluded.content_hash,
              last_synced = excluded.last_synced
            """,
            (path, notion_page_id, content_hash, 1 if is_folder else 0, last_synced),
        )


def all_paths() -> set[str]:
    with connect() as c:
        return {row["path"] for row in c.execute("SELECT path FROM pages")}


def delete_path(path: str):
    with connect() as c:
        c.execute("DELETE FROM pages WHERE path = ?", (path,))
