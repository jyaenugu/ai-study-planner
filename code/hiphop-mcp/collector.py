"""Poll Spotify recently-played and store new plays. Run by systemd timer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import requests
from db import connect
from spotify_token import get_access_token


def fetch_recent(limit=50):
    r = requests.get(
        "https://api.spotify.com/v1/me/player/recently-played",
        params={"limit": limit},
        headers={"Authorization": f"Bearer {get_access_token()}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["items"]


def store(items):
    inserted = 0
    with connect() as c:
        for item in items:
            t = item["track"]
            tid = t["id"]
            if not tid:
                continue
            c.execute(
                "INSERT OR REPLACE INTO tracks(id,name,artists,album,duration_ms) VALUES(?,?,?,?,?)",
                (
                    tid,
                    t["name"],
                    ", ".join(a["name"] for a in t["artists"]),
                    t["album"]["name"] if t.get("album") else None,
                    t["duration_ms"],
                ),
            )
            try:
                c.execute(
                    "INSERT INTO plays(track_id, played_at) VALUES(?,?)",
                    (tid, item["played_at"]),
                )
                inserted += 1
            except Exception:
                pass  # duplicate played_at
    return inserted


def main():
    items = fetch_recent()
    n = store(items)
    print(f"fetched={len(items)} inserted={n}")


if __name__ == "__main__":
    main()
