"""Generate GitHub-style OpenClaw usage SVG heatmap (daily cost) into Obsidian vault."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parser import session_durations

VAULT = Path.home() / "Documents" / "Obsidian Vault"
OUT = VAULT / "openclaw" / "usage-heatmap.svg"

CELL = 11
GAP = 2
WEEKS = 53
DAYS = 7
LEFT_PAD = 30
TOP_PAD = 20

# Purple palette to distinguish from music heatmap
COLORS = ["#ebedf0", "#d4c5f9", "#a371f7", "#8957e5", "#6e40c9"]
THRESH = [0, 1, 15, 60, 180]  # minutes of bot chat time


def bucket(minutes: float) -> int:
    for i in range(len(THRESH) - 1, -1, -1):
        if minutes >= THRESH[i]:
            return i
    return 0


def daily_minutes(start: dt.date, end: dt.date) -> dict[dt.date, float]:
    """Daily bot chat time in minutes (OpenClaw sessions only, idle gaps >5min excluded)."""
    in_range = lambda d: start.isoformat() <= d <= end.isoformat()
    durations = session_durations(date_filter=in_range)
    return {dt.date.fromisoformat(d): s / 60 for d, s in durations.items()}


def generate(end: dt.date | None = None) -> Path:
    end = end or dt.date.today()
    end_of_grid = end + dt.timedelta(days=(5 - end.weekday()) % 7)
    start = end_of_grid - dt.timedelta(days=WEEKS * 7 - 1)

    data = daily_minutes(start, end)
    width = LEFT_PAD + WEEKS * (CELL + GAP)
    height = TOP_PAD + DAYS * (CELL + GAP) + 40

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="-apple-system, sans-serif" font-size="9">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
    ]

    for i, label in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        y = TOP_PAD + i * (CELL + GAP) + CELL - 2
        parts.append(f'<text x="2" y="{y}" fill="#586069">{label}</text>')

    seen = set()
    for w in range(WEEKS):
        day0 = start + dt.timedelta(days=w * 7)
        if day0.month not in seen and day0.day <= 7:
            seen.add(day0.month)
            x = LEFT_PAD + w * (CELL + GAP)
            parts.append(f'<text x="{x}" y="{TOP_PAD - 6}" fill="#586069">{day0.strftime("%b")}</text>')

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

    legend_y = TOP_PAD + DAYS * (CELL + GAP) + 20
    parts.append(f'<text x="{LEFT_PAD}" y="{legend_y}" fill="#586069">Less</text>')
    for i, c in enumerate(COLORS):
        x = LEFT_PAD + 30 + i * (CELL + GAP)
        parts.append(f'<rect x="{x}" y="{legend_y - 9}" width="{CELL}" height="{CELL}" rx="2" fill="{c}"/>')
    x_more = LEFT_PAD + 30 + len(COLORS) * (CELL + GAP) + 2
    parts.append(f'<text x="{x_more}" y="{legend_y}" fill="#586069">More</text>')

    parts.append("</svg>")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts))
    return OUT


if __name__ == "__main__":
    p = generate()
    print(f"wrote {p}")
