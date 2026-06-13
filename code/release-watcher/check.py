#!/usr/bin/env python3
"""Coin's release watcher — detect new Spotify releases from artists Han listens to.

Runs daily via systemd timer. Picks top artists from last 30 days of plays,
queries Spotify for their recent albums/singles, and notifies Telegram +
writes a Brain insight note for anything new (released within last 14 days
and not seen before). First run silently records baseline so we don't spam
old releases.
"""
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path
from urllib import parse, request

sys.path.insert(0, str(Path.home() / "openclaw-tools" / "hiphop-mcp"))
sys.path.insert(0, str(Path.home() / "openclaw-tools" / "brain-mcp"))
sys.path.insert(0, str(Path.home() / "openclaw-tools"))

import requests
from spotify_token import get_access_token

CONFIG = Path.home() / ".openclaw" / "openclaw.json"
SPOTIFY_DB = Path.home() / "openclaw-tools" / "data" / "spotify.db"
STATE = Path.home() / "openclaw-tools" / "data" / "release_watcher_state.json"
KST = dt.timezone(dt.timedelta(hours=9))
API = "https://api.spotify.com/v1"
LOOKBACK_DAYS = 14
TOP_ARTIST_COUNT = 10
PLAYS_LOOKBACK_DAYS = 30


def _hdr() -> dict:
    return {"Authorization": f"Bearer {get_access_token()}"}


def _telegram_creds() -> tuple[str, str]:
    cfg = json.loads(CONFIG.read_text())
    token = cfg["channels"]["telegram"]["botToken"]
    chat = cfg["commands"]["ownerAllowFrom"][0]
    chat_id = chat.split(":", 1)[1] if ":" in chat else chat
    return token, chat_id


def _send_telegram(text: str):
    token, chat_id = _telegram_creds()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "false"}).encode()
    with request.urlopen(url, data=payload, timeout=15) as r:
        r.read()


def _load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"initialized": False, "seen_release_ids": []}


def _save_state(s: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2))


def _top_artists() -> list[str]:
    if not SPOTIFY_DB.exists():
        return []
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=PLAYS_LOOKBACK_DAYS)).isoformat()
    with sqlite3.connect(SPOTIFY_DB) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT t.artists, COUNT(*) AS plays
            FROM plays p JOIN tracks t ON p.track_id = t.id
            WHERE p.played_at >= ?
            GROUP BY t.artists
            ORDER BY plays DESC
            LIMIT ?
            """,
            (cutoff, TOP_ARTIST_COUNT * 3),
        ).fetchall()
    seen = set()
    artists = []
    for r in rows:
        # tracks.artists is comma-separated; take primary (first)
        primary = r["artists"].split(",")[0].strip()
        if primary and primary not in seen:
            seen.add(primary)
            artists.append(primary)
        if len(artists) >= TOP_ARTIST_COUNT:
            break
    return artists


def _search_artist_id(name: str) -> str | None:
    try:
        r = requests.get(
            f"{API}/search",
            headers=_hdr(),
            params={"q": name, "type": "artist", "limit": 1},
            timeout=15,
        )
        items = r.json().get("artists", {}).get("items", [])
        return items[0]["id"] if items else None
    except Exception as e:
        print(f"search '{name}' failed: {e}", file=sys.stderr)
        return None


def _latest_releases(artist_id: str, limit: int = 5) -> list[dict]:
    try:
        r = requests.get(
            f"{API}/artists/{artist_id}/albums",
            headers=_hdr(),
            params={"include_groups": "album,single", "limit": limit, "market": "KR"},
            timeout=15,
        )
        return r.json().get("items", [])
    except Exception as e:
        print(f"releases for {artist_id} failed: {e}", file=sys.stderr)
        return []


def main():
    state = _load_state()
    seen: set[str] = set(state.get("seen_release_ids", []))
    cutoff_date = (dt.date.today() - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()

    new_items = []
    all_ids: list[str] = []
    for artist in _top_artists():
        aid = _search_artist_id(artist)
        if not aid:
            continue
        for rel in _latest_releases(aid):
            rid = rel["id"]
            all_ids.append(rid)
            release_date = rel.get("release_date", "")
            if release_date < cutoff_date:
                continue
            if rid in seen:
                continue
            new_items.append({
                "artist": artist,
                "title": rel.get("name", "?"),
                "type": rel.get("album_type", "?"),
                "date": release_date,
                "url": rel.get("external_urls", {}).get("spotify", ""),
                "id": rid,
            })

    # First run: silently establish baseline, no notification spam
    if not state.get("initialized"):
        state["initialized"] = True
        state["seen_release_ids"] = all_ids[-300:]
        _save_state(state)
        print(f"baseline saved ({len(all_ids)} releases recorded as seen)")
        return

    if new_items:
        lines = [f"🪙 새 release · {dt.date.today().isoformat()}"]
        for it in new_items[:10]:
            badge = "💿" if it["type"] == "album" else "🎵"
            lines.append(f"{badge} {it['artist']} — {it['title']} ({it['date']})")
            if it["url"]:
                lines.append(f"  {it['url']}")
        _send_telegram("\n".join(lines))

        # Persist as Brain insight note
        try:
            import server as brain  # brain-mcp on sys.path
            body = "\n".join(
                f"- {it['artist']}: **{it['title']}** ({it['type']}, {it['date']}) {it['url']}"
                for it in new_items
            )
            brain.note(
                kind="insight",
                title=f"새 release 알림 ({dt.date.today().isoformat()})",
                content=body,
                tags=["spotify", "release", "discovery"],
            )
        except Exception as e:
            print(f"brain note failed: {e}", file=sys.stderr)

        seen.update(it["id"] for it in new_items)

    state["seen_release_ids"] = list(seen)[-300:]
    _save_state(state)
    print(f"checked. new={len(new_items)} total_seen={len(seen)}")


if __name__ == "__main__":
    main()
