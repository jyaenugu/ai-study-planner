"""Write per-day listening summary to Obsidian Daily/YYYY-MM-DD.md.

Times are KST. DB stores UTC; we convert with date(played_at, '+9 hours').
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import connect

VAULT = Path.home() / "Documents" / "Obsidian Vault"
DAILY_DIR = VAULT / "Daily"

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def _fetch_day(date_iso: str) -> dict:
    with connect() as c:
        summary = c.execute(
            """
            SELECT
              COALESCE(SUM(t.duration_ms), 0) AS ms,
              COUNT(*) AS plays,
              COUNT(DISTINCT p.track_id) AS unique_tracks
            FROM plays p JOIN tracks t ON p.track_id = t.id
            WHERE date(p.played_at, '+9 hours') = ?
            """,
            (date_iso,),
        ).fetchone()

        by_track = c.execute(
            """
            SELECT t.name, t.artists, COUNT(*) AS plays
            FROM plays p JOIN tracks t ON p.track_id = t.id
            WHERE date(p.played_at, '+9 hours') = ?
            GROUP BY p.track_id
            ORDER BY plays DESC, t.name
            """,
            (date_iso,),
        ).fetchall()

        timeline = c.execute(
            """
            SELECT time(p.played_at, '+9 hours') AS hhmmss, t.name, t.artists
            FROM plays p JOIN tracks t ON p.track_id = t.id
            WHERE date(p.played_at, '+9 hours') = ?
            ORDER BY p.played_at ASC
            """,
            (date_iso,),
        ).fetchall()

    return {
        "minutes": round(summary["ms"] / 60000, 1) if summary else 0,
        "plays": summary["plays"] if summary else 0,
        "unique_tracks": summary["unique_tracks"] if summary else 0,
        "by_track": [dict(r) for r in by_track],
        "timeline": [dict(r) for r in timeline],
    }


def render(date_iso: str, data: dict) -> str:
    d = dt.date.fromisoformat(date_iso)
    weekday = WEEKDAY_KR[d.weekday()]

    obsessed = [r for r in data["by_track"] if r["plays"] >= 3]
    top5 = data["by_track"][:5]

    lines = [
        f"# {date_iso} ({weekday})",
        "",
        f"**청취 시간:** {data['minutes']}분  ",
        f"**재생 횟수:** {data['plays']} · {data['unique_tracks']}곡 (unique)",
        "",
        "## 꽂힌 곡 (3회 이상)",
    ]
    if obsessed:
        for r in obsessed:
            lines.append(f"- {r['plays']}x — **{r['name']}** · {r['artists']}")
    else:
        lines.append("- (없음)")

    lines += ["", "## Top 5"]
    if top5:
        for i, r in enumerate(top5, 1):
            lines.append(f"{i}. {r['plays']}x — {r['name']} · {r['artists']}")
    else:
        lines.append("- (재생 없음)")

    lines += ["", "## 전체 재생 (시간순, KST)"]
    if data["timeline"]:
        for r in data["timeline"]:
            hhmm = r["hhmmss"][:5]
            lines.append(f"- `{hhmm}` {r['name']} · {r['artists']}")
    else:
        lines.append("- (재생 없음)")

    lines.append("")
    return "\n".join(lines)


def write_note(date_iso: str) -> Path:
    data = _fetch_day(date_iso)
    md = render(date_iso, data)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    path = DAILY_DIR / f"{date_iso}.md"
    path.write_text(md)
    return path


def backfill(days: int = 30) -> list[Path]:
    today = dt.date.today()
    written = []
    for i in range(days):
        d = today - dt.timedelta(days=i)
        with connect() as c:
            n = c.execute(
                "SELECT COUNT(*) AS n FROM plays WHERE date(played_at, '+9 hours') = ?",
                (d.isoformat(),),
            ).fetchone()["n"]
        if n == 0:
            continue
        written.append(write_note(d.isoformat()))
    return written


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--yesterday":
        target = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        p = write_note(target)
        print(f"wrote {p}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--backfill":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        paths = backfill(days)
        for p in paths:
            print(f"wrote {p}")
        print(f"total: {len(paths)} notes")
    else:
        p = write_note(dt.date.today().isoformat())
        print(f"wrote {p}")
