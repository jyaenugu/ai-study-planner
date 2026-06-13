#!/usr/bin/env python3
"""spotify MCP server. Tools for Spotify obsession tracking, playback, playlists, and heatmap."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
import requests
from mcp.server.fastmcp import FastMCP
from db import connect
from spotify_token import get_access_token
from usage_logger import logged

mcp = FastMCP("spotify")
API = "https://api.spotify.com/v1"


def _hdr():
    return {"Authorization": f"Bearer {get_access_token()}"}


def _today_iso():
    return dt.date.today().isoformat()


# ---------- Obsession tracking ----------

@mcp.tool()
@logged("spotify")
def today_obsessed(min_plays: int = 3) -> list[dict]:
    """오늘 N번 이상 들은 곡 (기본 3회). Returns list of {track, artist, plays}."""
    return obsessed_on(_today_iso(), min_plays)


@mcp.tool()
@logged("spotify")
def obsessed_on(date: str, min_plays: int = 3) -> list[dict]:
    """특정 날짜(KST, YYYY-MM-DD)에 N번 이상 들은 곡."""
    with connect() as c:
        rows = c.execute(
            """
            SELECT t.name, t.artists, COUNT(*) as plays
            FROM plays p JOIN tracks t ON p.track_id = t.id
            WHERE date(p.played_at, '+9 hours') = ?
            GROUP BY t.id
            HAVING plays >= ?
            ORDER BY plays DESC, t.name
            """,
            (date, min_plays),
        ).fetchall()
    return [{"track": r["name"], "artist": r["artists"], "plays": r["plays"]} for r in rows]


@mcp.tool()
@logged("spotify")
def listening_time(date: str | None = None) -> dict:
    """특정 날짜(KST, YYYY-MM-DD)의 총 청취 시간. date 생략 시 오늘."""
    d = date or _today_iso()
    with connect() as c:
        row = c.execute(
            """
            SELECT COALESCE(SUM(t.duration_ms), 0) as ms, COUNT(*) as count
            FROM plays p JOIN tracks t ON p.track_id = t.id
            WHERE date(p.played_at, '+9 hours') = ?
            """,
            (d,),
        ).fetchone()
    minutes = round(row["ms"] / 60000, 1)
    return {"date": d, "minutes": minutes, "tracks_played": row["count"]}


# ---------- Playback ----------

@mcp.tool()
@logged("spotify")
def now_playing() -> dict:
    """지금 재생 중인 곡 정보."""
    r = requests.get(f"{API}/me/player/currently-playing", headers=_hdr(), timeout=10)
    if r.status_code == 204:
        return {"playing": False}
    r.raise_for_status()
    d = r.json()
    if not d.get("item"):
        return {"playing": False}
    t = d["item"]
    return {
        "playing": d.get("is_playing", False),
        "track": t["name"],
        "artist": ", ".join(a["name"] for a in t["artists"]),
        "album": t["album"]["name"],
        "progress_ms": d.get("progress_ms"),
        "duration_ms": t["duration_ms"],
    }


def _search_track_uri(query: str) -> tuple[str, str]:
    r = requests.get(
        f"{API}/search",
        params={"q": query, "type": "track", "limit": 1},
        headers=_hdr(),
        timeout=10,
    )
    r.raise_for_status()
    items = r.json()["tracks"]["items"]
    if not items:
        raise RuntimeError(f"검색 결과 없음: {query}")
    t = items[0]
    return t["uri"], f'{t["name"]} — {", ".join(a["name"] for a in t["artists"])}'


@mcp.tool()
@logged("spotify")
def play(query: str) -> dict:
    """검색해서 재생. Premium 필요."""
    uri, label = _search_track_uri(query)
    r = requests.put(
        f"{API}/me/player/play",
        json={"uris": [uri]},
        headers=_hdr(),
        timeout=10,
    )
    if r.status_code not in (200, 202, 204):
        raise RuntimeError(f"{r.status_code}: {r.text}")
    return {"ok": True, "playing": label}


@mcp.tool()
@logged("spotify")
def pause() -> dict:
    """일시정지."""
    r = requests.put(f"{API}/me/player/pause", headers=_hdr(), timeout=10)
    return {"ok": r.status_code in (200, 202, 204)}


@mcp.tool()
@logged("spotify")
def resume() -> dict:
    """재생 재개."""
    r = requests.put(f"{API}/me/player/play", headers=_hdr(), timeout=10)
    return {"ok": r.status_code in (200, 202, 204)}


@mcp.tool()
@logged("spotify")
def skip() -> dict:
    """다음 곡."""
    r = requests.post(f"{API}/me/player/next", headers=_hdr(), timeout=10)
    return {"ok": r.status_code in (200, 202, 204)}


@mcp.tool()
@logged("spotify")
def queue(query: str) -> dict:
    """검색해서 큐에 추가."""
    uri, label = _search_track_uri(query)
    r = requests.post(
        f"{API}/me/player/queue",
        params={"uri": uri},
        headers=_hdr(),
        timeout=10,
    )
    if r.status_code not in (200, 202, 204):
        raise RuntimeError(f"{r.status_code}: {r.text}")
    return {"ok": True, "queued": label}


# ---------- Playlists ----------

def _me_id():
    r = requests.get(f"{API}/me", headers=_hdr(), timeout=10)
    r.raise_for_status()
    return r.json()["id"]


def _find_playlist(name: str) -> dict | None:
    url = f"{API}/me/playlists?limit=50"
    while url:
        r = requests.get(url, headers=_hdr(), timeout=10)
        r.raise_for_status()
        d = r.json()
        for p in d["items"]:
            if p["name"].lower() == name.lower():
                return p
        url = d.get("next")
    return None


@mcp.tool()
@logged("spotify")
def playlists() -> list[dict]:
    """내 플레이리스트 목록."""
    r = requests.get(f"{API}/me/playlists", params={"limit": 50}, headers=_hdr(), timeout=10)
    r.raise_for_status()
    return [{"name": p["name"], "tracks": p["tracks"]["total"], "id": p["id"]} for p in r.json()["items"]]


@mcp.tool()
@logged("spotify")
def playlist_add(playlist_name: str, query: str) -> dict:
    """검색한 곡을 지정 플레이리스트에 추가 (이름으로 찾음)."""
    p = _find_playlist(playlist_name)
    if not p:
        raise RuntimeError(f"플레이리스트 없음: {playlist_name}")
    uri, label = _search_track_uri(query)
    r = requests.post(
        f"{API}/playlists/{p['id']}/tracks",
        json={"uris": [uri]},
        headers=_hdr(),
        timeout=10,
    )
    r.raise_for_status()
    return {"ok": True, "added": label, "playlist": p["name"]}


@mcp.tool()
@logged("spotify")
def playlist_create(name: str, description: str = "", public: bool = False) -> dict:
    """플레이리스트 생성."""
    uid = _me_id()
    r = requests.post(
        f"{API}/users/{uid}/playlists",
        json={"name": name, "description": description, "public": public},
        headers=_hdr(),
        timeout=10,
    )
    r.raise_for_status()
    d = r.json()
    return {"ok": True, "name": d["name"], "id": d["id"]}


# ---------- Heatmap ----------

@mcp.tool()
@logged("spotify")
def heatmap_generate() -> dict:
    """청취 시간 잔디밭 SVG를 Obsidian vault에 생성."""
    from heatmap import generate
    path = generate()
    return {"ok": True, "path": str(path)}


# ---------- Daily notes ----------

@mcp.tool()
@logged("spotify")
def daily_note_write(date: str | None = None) -> dict:
    """그 날짜(KST, YYYY-MM-DD)의 청취 기록을 Daily/YYYY-MM-DD.md로 작성. date 생략 시 오늘."""
    from daily_note import write_note
    d = date or _today_iso()
    path = write_note(d)
    return {"ok": True, "date": d, "path": str(path)}


@mcp.tool()
@logged("spotify")
def daily_note_backfill(days: int = 30) -> dict:
    """지난 N일 중 재생 기록이 있는 날짜에 대해 Daily 노트를 일괄 생성."""
    from daily_note import backfill
    paths = backfill(days)
    return {"ok": True, "written": [str(p) for p in paths], "count": len(paths)}


if __name__ == "__main__":
    mcp.run()
