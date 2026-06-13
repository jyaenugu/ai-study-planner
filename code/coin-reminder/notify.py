#!/usr/bin/env python3
"""Coin block reminder — runs every few minutes via systemd timer.

Checks schedule.db for an upcoming block within ~10 minutes and pushes
a short notification to Telegram via the bot API. No LLM call, no cost.
State file keeps the last notified block_id so the same block isn't
re-notified on every tick.
"""
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path
from urllib import error, parse, request

CONFIG = Path.home() / ".openclaw" / "openclaw.json"
SCHEDULE_DB = Path.home() / "openclaw-tools" / "data" / "schedule.db"
STATE = Path.home() / "openclaw-tools" / "data" / "coin_reminder_state.json"
KST = dt.timezone(dt.timedelta(hours=9))
WITHIN_MIN = 10


def _telegram_creds() -> tuple[str, str]:
    cfg = json.loads(CONFIG.read_text())
    token = cfg["channels"]["telegram"]["botToken"]
    allow = cfg["commands"]["ownerAllowFrom"][0]
    chat_id = allow.split(":", 1)[1] if ":" in allow else allow
    return token, chat_id


def _load_state() -> dict:
    if not STATE.exists():
        return {"last_block_id": None}
    return json.loads(STATE.read_text())


def _save_state(state: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state))


def _send(text: str):
    token, chat_id = _telegram_creds()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        with request.urlopen(url, data=payload, timeout=15) as r:
            r.read()
    except error.URLError as e:
        print(f"telegram send failed: {e}", file=sys.stderr)
        sys.exit(1)


def _next_block() -> dict | None:
    if not SCHEDULE_DB.exists():
        return None
    now = dt.datetime.now(KST)
    cutoff = now + dt.timedelta(minutes=WITHIN_MIN)
    with sqlite3.connect(SCHEDULE_DB) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            """
            SELECT b.*, a.icon, a.description
            FROM blocks b LEFT JOIN activities a ON b.activity = a.name
            WHERE b.start_at > ? AND b.start_at <= ? AND b.completed_at IS NULL
            ORDER BY b.start_at LIMIT 1
            """,
            (now.isoformat(), cutoff.isoformat()),
        ).fetchone()
    return dict(row) if row else None


def main():
    block = _next_block()
    if not block:
        return
    state = _load_state()
    if state.get("last_block_id") == block["id"]:
        return
    start = dt.datetime.fromisoformat(block["start_at"])
    now = dt.datetime.now(KST)
    mins = max(0, int((start - now).total_seconds() / 60))
    icon = block.get("icon") or "•"
    notes = block.get("notes")
    when = "곧" if mins == 0 else f"{mins}분 뒤"
    text = f"🪙 {when} {icon} {block['activity']}"
    if notes:
        text += f" — {notes}"
    _send(text)
    state["last_block_id"] = block["id"]
    _save_state(state)


if __name__ == "__main__":
    main()
