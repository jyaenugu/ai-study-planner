"""Mirror Obsidian Vault to Notion.

Folder tree → child pages. Each .md file → a child page with content blocks.
Tracks path → notion_page_id + content_hash in SQLite. Only changed files
are re-synced. Files/folders removed from the Vault get archived in Notion.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sys
import time
from pathlib import Path

from notion_client import Client
from notion_client.errors import APIResponseError

import config
import db
import markdown_to_blocks as mdblocks

CHUNK = 100  # Notion API: max 100 blocks per append request


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _title_rt(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text[:2000]}}]


def _retry(fn, *args, **kwargs):
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except APIResponseError as e:
            if e.status == 429:
                wait = 2 ** attempt
                print(f"  rate limited, sleeping {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("retries exhausted")


def _create_page(notion: Client, parent_id: str, title: str, blocks: list[dict]) -> str:
    first_chunk = blocks[:CHUNK]
    page = _retry(
        notion.pages.create,
        parent={"page_id": parent_id},
        properties={"title": {"title": _title_rt(title)}},
        children=first_chunk,
    )
    page_id = page["id"]
    for i in range(CHUNK, len(blocks), CHUNK):
        _retry(notion.blocks.children.append, block_id=page_id, children=blocks[i:i + CHUNK])
        time.sleep(0.34)  # ~3 req/s rate limit
    return page_id


def _replace_children(notion: Client, page_id: str, blocks: list[dict]):
    cursor = None
    to_archive = []
    while True:
        resp = _retry(notion.blocks.children.list, block_id=page_id, start_cursor=cursor)
        to_archive.extend(b["id"] for b in resp["results"])
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    for bid in to_archive:
        _retry(notion.blocks.delete, block_id=bid)
        time.sleep(0.34)
    for i in range(0, len(blocks), CHUNK):
        _retry(notion.blocks.children.append, block_id=page_id, children=blocks[i:i + CHUNK])
        time.sleep(0.34)


def _archive_page(notion: Client, page_id: str):
    try:
        _retry(notion.pages.update, page_id=page_id, archived=True)
    except APIResponseError as e:
        print(f"  failed to archive {page_id}: {e}", file=sys.stderr)


def _walk_vault(root: Path):
    """Yield (rel_path, abs_path, is_dir) in deterministic order, deepest-last."""
    def visit(p: Path, rel: Path):
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        for e in entries:
            if e.name in config.IGNORE_FILES:
                continue
            if e.is_dir():
                if e.name in config.IGNORE_DIRS:
                    continue
                child_rel = rel / e.name
                yield (str(child_rel), e, True)
                yield from visit(e, child_rel)
            elif e.is_file() and e.suffix.lower() == ".md":
                child_rel = rel / e.name
                yield (str(child_rel), e, False)

    yield from visit(root, Path("."))


def sync(verbose: bool = True):
    cfg = config.load()
    notion = Client(auth=cfg["token"])
    parent_id = cfg["parent_page_id"]

    seen_paths: set[str] = set()
    stats = {"created": 0, "updated": 0, "unchanged": 0, "archived": 0, "folders": 0}

    for rel, abs_path, is_dir in _walk_vault(config.VAULT_PATH):
        seen_paths.add(rel)
        parent_rel = str(Path(rel).parent)
        if parent_rel == ".":
            parent_notion_id = parent_id
        else:
            parent_row = db.get_page(parent_rel)
            if not parent_row:
                print(f"  skip {rel}: parent folder not synced yet", file=sys.stderr)
                continue
            parent_notion_id = parent_row["notion_page_id"]

        existing = db.get_page(rel)
        title = Path(rel).stem if not is_dir else Path(rel).name

        if is_dir:
            if existing:
                stats["folders"] += 1
                continue
            if verbose:
                print(f"+ folder: {rel}")
            page_id = _create_page(notion, parent_notion_id, title, [])
            db.upsert_page(rel, page_id, None, True, _now())
            stats["folders"] += 1
            stats["created"] += 1
            continue

        text = abs_path.read_text(encoding="utf-8")
        h = _hash(text)
        blocks = mdblocks.render(text)

        if existing and existing["content_hash"] == h:
            stats["unchanged"] += 1
            continue

        if existing:
            if verbose:
                print(f"~ update: {rel}")
            _replace_children(notion, existing["notion_page_id"], blocks)
            db.upsert_page(rel, existing["notion_page_id"], h, False, _now())
            stats["updated"] += 1
        else:
            if verbose:
                print(f"+ create: {rel}")
            page_id = _create_page(notion, parent_notion_id, title, blocks)
            db.upsert_page(rel, page_id, h, False, _now())
            stats["created"] += 1

    for path in db.all_paths() - seen_paths:
        row = db.get_page(path)
        if not row:
            continue
        if verbose:
            print(f"- archive: {path}")
        _archive_page(notion, row["notion_page_id"])
        db.delete_path(path)
        stats["archived"] += 1

    print(
        f"done: created={stats['created']} updated={stats['updated']} "
        f"unchanged={stats['unchanged']} archived={stats['archived']} "
        f"folders={stats['folders']}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    sync(verbose=not args.quiet)


if __name__ == "__main__":
    main()
