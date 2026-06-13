"""Generate GitHub-style listening time SVG heatmap into Obsidian vault.

Times are KST. DB stores UTC; queries convert with date(played_at, '+9 hours').
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import connect

VAULT = Path.home() / "Documents" / "Obsidian Vault"
OUT = VAULT / "Music" / "listening-heatmap.svg"

CELL = 11
GAP = 2
WEEKS = 53
DAYS = 7
LEFT_PAD = 30
TOP_PAD = 20
SUMMARY_ROWS = 7  # recent days listed under the grid

# GitHub green
COLORS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
THRESH = [0, 1, 30, 90, 180]  # minutes


def bucket(minutes: float) -> int:
    for i in range(len(THRESH) - 1, -1, -1):
        if minutes >= THRESH[i]:
            return i
    return 0


def daily_minutes(start: dt.date, end: dt.date) -> dict[dt.date, float]:
    with connect() as c:
        rows = c.execute(
            """
            SELECT date(p.played_at, '+9 hours') AS d, SUM(t.duration_ms) AS ms
            FROM plays p JOIN tracks t ON p.track_id = t.id
            WHERE date(p.played_at, '+9 hours') BETWEEN ? AND ?
            GROUP BY d
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    return {dt.date.fromisoformat(r["d"]): r["ms"] / 60000 for r in rows}


def generate(end: dt.date | None = None) -> Path:
    end = end or dt.date.today()
    # Anchor grid to this week's Saturday so today's cell is always inside.
    end_of_grid = end + dt.timedelta(days=(5 - end.weekday()) % 7)
    start = end_of_grid - dt.timedelta(days=WEEKS * 7 - 1)

    data = daily_minutes(start, end)

    width = LEFT_PAD + WEEKS * (CELL + GAP)
    grid_bottom = TOP_PAD + DAYS * (CELL + GAP)
    height = grid_bottom + 40 + SUMMARY_ROWS * 14 + 20

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="-apple-system, sans-serif" font-size="9">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
    ]

    for i, label in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        y = TOP_PAD + i * (CELL + GAP) + CELL - 2
        parts.append(f'<text x="2" y="{y}" fill="#586069">{label}</text>')

    seen_months = set()
    for w in range(WEEKS):
        day0 = start + dt.timedelta(days=w * 7)
        if day0.month not in seen_months and day0.day <= 7:
            seen_months.add(day0.month)
            x = LEFT_PAD + w * (CELL + GAP)
            parts.append(
                f'<text x="{x}" y="{TOP_PAD - 6}" fill="#586069">{day0.strftime("%b")}</text>'
            )

    today = dt.date.today()
    for w in range(WEEKS):
        for d in range(DAYS):
            day = start + dt.timedelta(days=w * 7 + d)
            if day > today:
                continue
            mins = data.get(day, 0)
            color = COLORS[bucket(mins)]
            x = LEFT_PAD + w * (CELL + GAP)
            y = TOP_PAD + d * (CELL + GAP)
            tip = f"{day.isoformat()}: {mins:.0f} min"
            parts.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{color}">'
                f'<title>{tip}</title></rect>'
            )

    legend_y = grid_bottom + 20
    parts.append(f'<text x="{LEFT_PAD}" y="{legend_y}" fill="#586069">Less</text>')
    for i, c in enumerate(COLORS):
        x = LEFT_PAD + 30 + i * (CELL + GAP)
        parts.append(
            f'<rect x="{x}" y="{legend_y - 9}" width="{CELL}" height="{CELL}" rx="2" fill="{c}"/>'
        )
    x_more = LEFT_PAD + 30 + len(COLORS) * (CELL + GAP) + 2
    parts.append(f'<text x="{x_more}" y="{legend_y}" fill="#586069">More</text>')

    summary_top = grid_bottom + 40
    parts.append(
        f'<text x="{LEFT_PAD}" y="{summary_top}" fill="#24292e" font-weight="bold">Recent days (KST)</text>'
    )
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"]
    for i in range(SUMMARY_ROWS):
        day = today - dt.timedelta(days=i)
        mins = data.get(day, 0)
        row_y = summary_top + 14 * (i + 1)
        label = f"{day.isoformat()} ({weekday_kr[day.weekday()]})"
        parts.append(
            f'<text x="{LEFT_PAD}" y="{row_y}" fill="#24292e">{label}</text>'
            f'<text x="{LEFT_PAD + 120}" y="{row_y}" fill="#24292e" text-anchor="end">{mins:.1f} min</text>'
        )

    parts.append("</svg>")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts))
    return OUT


if __name__ == "__main__":
    p = generate()
    print(f"wrote {p}")
