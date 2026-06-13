#!/usr/bin/env python3
"""schedule MCP server — Coin이 서희님의 일상 활동 블록을 관리.

활동 카테고리: rap_practice, lyrics, midi, research, content, rest
DB: ~/openclaw-tools/data/schedule.db
"""
import calendar
import datetime as dt
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from usage_logger import logged

mcp = FastMCP("schedule")

DB_PATH = Path.home() / "openclaw-tools" / "data" / "schedule.db"
VAULT = Path.home() / "Documents" / "Obsidian Vault"
SCHEDULE_DIR = VAULT / "Schedule"
CALENDAR_DIR = SCHEDULE_DIR / "Calendar"
PLANS_DIR = VAULT / "Plans"
KST = dt.timezone(dt.timedelta(hours=9))
WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
MONTH_KR = ["", "1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"]

SEED_ACTIVITIES = [
    ("rap_practice", "🎤", 30, "랩 연습 (특정 곡 따라/플로우)"),
    ("lyrics", "✍️", 60, "가사 작성·수정"),
    ("midi", "🎹", 60, "미디·DAW·비트"),
    ("research", "🔬", 120, "메인. 보호."),
    ("content", "📰", 30, "블로그·뉴스·로그"),
    ("rest", "🌿", 20, "의식적 쉼"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
  name TEXT PRIMARY KEY,
  icon TEXT NOT NULL,
  default_min INTEGER NOT NULL,
  description TEXT
);

CREATE TABLE IF NOT EXISTS blocks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  activity TEXT NOT NULL,
  start_at TEXT NOT NULL,
  duration_min INTEGER NOT NULL,
  notes TEXT,
  completed_at TEXT,
  completion_note TEXT,
  FOREIGN KEY (activity) REFERENCES activities(name)
);

CREATE INDEX IF NOT EXISTS idx_blocks_start ON blocks(start_at);

CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  author_or_artist TEXT,
  status TEXT NOT NULL DEFAULT 'backlog',
  progress TEXT,
  notes TEXT,
  priority INTEGER NOT NULL DEFAULT 0,
  added_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_items_kind_status ON items(kind, status);

CREATE TABLE IF NOT EXISTS commitments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  when_at TEXT NOT NULL,
  duration_min INTEGER,
  where_at TEXT,
  with_whom TEXT,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'upcoming',
  category TEXT,
  added_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_commitments_when ON commitments(when_at);
"""

ITEM_KIND_ICON = {
    "book": "📚",
    "movie": "🎬",
    "series": "📺",
    "album": "💿",
    "podcast": "🎧",
    "project": "💼",
    "habit": "🔁",
    "course": "🎓",
    "paper": "📄",
}
ITEM_STATUSES = {"backlog", "in_progress", "done", "paused", "abandoned"}
COMMITMENT_STATUSES = {"upcoming", "completed", "cancelled"}

COMMITMENT_CATEGORY_ICON = {
    "class": "🎓",
    "exam": "📝",
    "presentation": "🎤",
    "meeting": "👥",
    "personal": "📌",
    "travel": "🚆",
    "other": "•",
}
COMMITMENT_CATEGORIES = set(COMMITMENT_CATEGORY_ICON)


def _auto_category(title: str) -> str:
    t = title.lower()
    if "수업" in title or "강의" in title:
        return "class"
    if "시험" in title or "고사" in title:
        return "exam"
    if "발표" in title:
        return "presentation"
    if "미팅" in title or "회의" in title or "meeting" in t:
        return "meeting"
    if "srt" in t or "ktx" in t or "본가" in title or "복귀" in title or "이동" in title:
        return "travel"
    return "personal"


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    # migrations: add columns if missing (for DBs created before category column was added)
    cols = {r[1] for r in con.execute("PRAGMA table_info(commitments)")}
    if "category" not in cols:
        con.execute("ALTER TABLE commitments ADD COLUMN category TEXT")
    # idempotent seed
    for name, icon, dmin, desc in SEED_ACTIVITIES:
        con.execute(
            "INSERT OR IGNORE INTO activities (name, icon, default_min, description) VALUES (?, ?, ?, ?)",
            (name, icon, dmin, desc),
        )
    # backfill category for existing rows
    for row in con.execute("SELECT id, title FROM commitments WHERE category IS NULL"):
        con.execute("UPDATE commitments SET category = ? WHERE id = ?", (_auto_category(row[1]), row[0]))
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _now() -> dt.datetime:
    return dt.datetime.now(KST)


def _parse_dt(s: str) -> dt.datetime:
    """Accept 'HH:MM' (today), 'YYYY-MM-DD HH:MM', or ISO."""
    s = s.strip()
    today = _now().date()
    if len(s) == 5 and s[2] == ":":
        h, m = int(s[:2]), int(s[3:])
        return dt.datetime(today.year, today.month, today.day, h, m, tzinfo=KST)
    if len(s) == 16 and s[10] == " ":
        d = dt.datetime.strptime(s, "%Y-%m-%d %H:%M")
        return d.replace(tzinfo=KST)
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=KST)
    return d.astimezone(KST)


def _fmt_block(row: sqlite3.Row, activities: dict) -> dict:
    act = activities.get(row["activity"], {})
    start = dt.datetime.fromisoformat(row["start_at"])
    end = start + dt.timedelta(minutes=row["duration_min"])
    return {
        "id": row["id"],
        "activity": row["activity"],
        "icon": act.get("icon", "•"),
        "start": start.strftime("%H:%M"),
        "end": end.strftime("%H:%M"),
        "date": start.date().isoformat(),
        "duration_min": row["duration_min"],
        "notes": row["notes"],
        "completed": row["completed_at"] is not None,
        "completion_note": row["completion_note"],
    }


def _activities_map(con) -> dict:
    return {
        r["name"]: {"icon": r["icon"], "default_min": r["default_min"], "description": r["description"]}
        for r in con.execute("SELECT * FROM activities")
    }


def _write_daily_note(con, date_iso: str):
    """Render Schedule/YYYY-MM-DD.md from current DB state for that date."""
    acts = _activities_map(con)
    rows = con.execute(
        "SELECT * FROM blocks WHERE date(start_at) = ? ORDER BY start_at",
        (date_iso,),
    ).fetchall()
    SCHEDULE_DIR.mkdir(parents=True, exist_ok=True)
    path = SCHEDULE_DIR / f"{date_iso}.md"
    d = dt.date.fromisoformat(date_iso)
    weekday = WEEKDAY_KR[d.weekday()]
    now_iso = _now().isoformat(timespec="seconds")
    lines = [
        "---",
        f"date: {date_iso}",
        f"day: {weekday}",
        f"generated: {now_iso}",
        "---",
        "",
        f"# 📅 {date_iso} ({weekday})",
        "",
    ]
    if not rows:
        lines.append("- (등록된 블록 없음)")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return
    total = len(rows)
    done = sum(1 for r in rows if r["completed_at"])
    lines.append(f"진행: **{done} / {total}** 완료")
    lines.append("")
    for r in rows:
        act = acts.get(r["activity"], {})
        icon = act.get("icon", "•")
        start = dt.datetime.fromisoformat(r["start_at"])
        end = start + dt.timedelta(minutes=r["duration_min"])
        box = "[x]" if r["completed_at"] else "[ ]"
        line = f"- {box} `{start.strftime('%H:%M')}–{end.strftime('%H:%M')}` {icon} **{r['activity']}**"
        if r["notes"]:
            line += f" — {r['notes']}"
        lines.append(line)
        if r["completed_at"]:
            done_at = dt.datetime.fromisoformat(r["completed_at"]).strftime("%H:%M")
            note = f", \"{r['completion_note']}\"" if r["completion_note"] else ""
            lines.append(f"    - ✓ {done_at} 완료{note}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_calendar(con, year: int, month: int):
    """Render Schedule/Calendar/YYYY-MM.md — month grid (Mon-first) with blocks + commitments per day."""
    CALENDAR_DIR.mkdir(parents=True, exist_ok=True)
    path = CALENDAR_DIR / f"{year:04d}-{month:02d}.md"

    acts = _activities_map(con)
    first = dt.date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    last = dt.date(year, month, last_day)

    block_rows = con.execute(
        "SELECT * FROM blocks WHERE date(start_at) >= ? AND date(start_at) <= ? ORDER BY start_at",
        (first.isoformat(), last.isoformat()),
    ).fetchall()
    blocks_by_day: dict[str, list] = {}
    for r in block_rows:
        d = dt.datetime.fromisoformat(r["start_at"]).date().isoformat()
        blocks_by_day.setdefault(d, []).append(r)

    comm_rows = con.execute(
        "SELECT * FROM commitments WHERE date(when_at) >= ? AND date(when_at) <= ? AND status = 'upcoming' ORDER BY when_at",
        (first.isoformat(), last.isoformat()),
    ).fetchall()
    comms_by_day: dict[str, list] = {}
    for r in comm_rows:
        d = dt.datetime.fromisoformat(r["when_at"]).date().isoformat()
        comms_by_day.setdefault(d, []).append(r)

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)

    prev_link = (first - dt.timedelta(days=1)).strftime("%Y-%m")
    next_link = (last + dt.timedelta(days=1)).strftime("%Y-%m")

    lines = [
        "---",
        f"month: {year}-{month:02d}",
        f"generated: {_now().isoformat(timespec='seconds')}",
        "---",
        "",
        f"# 📅 {year}년 {MONTH_KR[month]}",
        "",
        "| 월 | 화 | 수 | 목 | 금 | 토 | 일 |",
        "|---|---|---|---|---|---|---|",
    ]
    for week in weeks:
        cells = []
        for day_num in week:
            if day_num == 0:
                cells.append(" ")
                continue
            d_iso = f"{year:04d}-{month:02d}-{day_num:02d}"
            day_link = f"[[Schedule/{d_iso}\\|**{day_num}**]]"
            badges: list[str] = []
            for c in comms_by_day.get(d_iso, []):
                t = dt.datetime.fromisoformat(c["when_at"])
                title_short = c["title"][:10]
                cat_icon = COMMITMENT_CATEGORY_ICON.get(c["category"] or "personal", "📌")
                badges.append(f"{cat_icon}{t.strftime('%H:%M')} {title_short}")
            for b in blocks_by_day.get(d_iso, []):
                icon = acts.get(b["activity"], {}).get("icon", "•")
                t = dt.datetime.fromisoformat(b["start_at"])
                badges.append(f"{icon}{t.strftime('%H:%M')}")
            cell = day_link
            if badges:
                cell += "<br>" + "<br>".join(badges)
            cells.append(cell)
        lines.append("| " + " | ".join(cells) + " |")

    lines += [
        "",
        f"← [[Schedule/Calendar/{prev_link}\\|이전 달]] · [[Schedule/Calendar/{next_link}\\|다음 달]] →",
        "",
        "## 이번 달 약속",
        "",
    ]
    if not comm_rows:
        lines.append("- (없음)")
    for r in comm_rows:
        when = dt.datetime.fromisoformat(r["when_at"])
        day = WEEKDAY_KR[when.weekday()]
        s = f"- **{when.strftime('%m-%d')} ({day}) {when.strftime('%H:%M')}** — {r['title']}"
        bits = []
        if r["with_whom"]:
            bits.append(f"with {r['with_whom']}")
        if r["where_at"]:
            bits.append(f"@ {r['where_at']}")
        if bits:
            s += f" ({', '.join(bits)})"
        lines.append(s)

    path.write_text("\n".join(lines), encoding="utf-8")


def _rewrite_calendars_for(con, dates: list[str]):
    """Rewrite calendars for unique (year, month) pairs given a list of date-iso strings."""
    seen = set()
    for d in dates:
        if not d:
            continue
        try:
            ymd = dt.date.fromisoformat(d[:10])
        except ValueError:
            continue
        key = (ymd.year, ymd.month)
        if key in seen:
            continue
        seen.add(key)
        _write_calendar(con, ymd.year, ymd.month)


# ---------- Tools ----------

@mcp.tool()
@logged("schedule")
def activities() -> list[dict]:
    """등록된 활동 카테고리 목록."""
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT name, icon, default_min, description FROM activities ORDER BY name")]


@mcp.tool()
@logged("schedule")
def add_block(
    activity: str,
    start: str,
    duration_min: int | None = None,
    notes: str | None = None,
) -> dict:
    """일정 블록 추가.

    activity: rap_practice | lyrics | midi | research | content | rest
    start: 'HH:MM' (오늘) 또는 'YYYY-MM-DD HH:MM' 또는 ISO
    duration_min: 생략 시 활동의 default_min 사용
    notes: 메모 (예: "Drake - One Dance 플로우 따라")
    """
    with connect() as c:
        act = c.execute("SELECT * FROM activities WHERE name = ?", (activity,)).fetchone()
        if not act:
            return {"error": f"unknown activity '{activity}'. valid: {sorted(a['name'] for a in c.execute('SELECT name FROM activities'))}"}
        start_dt = _parse_dt(start)
        dur = duration_min or act["default_min"]
        cur = c.execute(
            "INSERT INTO blocks (activity, start_at, duration_min, notes) VALUES (?, ?, ?, ?)",
            (activity, start_dt.isoformat(), dur, notes),
        )
        block_id = cur.lastrowid
        row = c.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()
        _write_daily_note(c, start_dt.date().isoformat())
        _rewrite_calendars_for(c, [start_dt.date().isoformat()])
        return _fmt_block(row, _activities_map(c))


@mcp.tool()
@logged("schedule")
def plan_today(blocks: list[dict]) -> dict:
    """오늘 일정을 한 번에 짜기. 기존 오늘 미완료 블록은 삭제 후 새로 입력.

    blocks: [{activity, start ("HH:MM"), duration_min?, notes?}, ...]
    """
    today_iso = _now().date().isoformat()
    with connect() as c:
        c.execute(
            "DELETE FROM blocks WHERE date(start_at) = ? AND completed_at IS NULL",
            (today_iso,),
        )
        acts = _activities_map(c)
        added = []
        for b in blocks:
            act_name = b.get("activity")
            if act_name not in acts:
                return {"error": f"unknown activity '{act_name}'"}
            start_dt = _parse_dt(b["start"])
            dur = b.get("duration_min") or acts[act_name]["default_min"]
            cur = c.execute(
                "INSERT INTO blocks (activity, start_at, duration_min, notes) VALUES (?, ?, ?, ?)",
                (act_name, start_dt.isoformat(), dur, b.get("notes")),
            )
            row = c.execute("SELECT * FROM blocks WHERE id = ?", (cur.lastrowid,)).fetchone()
            added.append(_fmt_block(row, acts))
        _write_daily_note(c, today_iso)
        _rewrite_calendars_for(c, [today_iso])
    return {"date": today_iso, "blocks": added}


@mcp.tool()
@logged("schedule")
def today() -> list[dict]:
    """오늘 일정 (시간순)."""
    today_iso = _now().date().isoformat()
    with connect() as c:
        acts = _activities_map(c)
        rows = c.execute(
            "SELECT * FROM blocks WHERE date(start_at) = ? ORDER BY start_at",
            (today_iso,),
        ).fetchall()
        return [_fmt_block(r, acts) for r in rows]


@mcp.tool()
@logged("schedule")
def next_block(within_min: int = 90) -> dict | None:
    """다음 예정 블록. within_min 분 안에 시작하는 블록만 반환."""
    now = _now()
    cutoff = now + dt.timedelta(minutes=within_min)
    with connect() as c:
        acts = _activities_map(c)
        row = c.execute(
            "SELECT * FROM blocks WHERE start_at > ? AND start_at <= ? AND completed_at IS NULL ORDER BY start_at LIMIT 1",
            (now.isoformat(), cutoff.isoformat()),
        ).fetchone()
        return _fmt_block(row, acts) if row else None


@mcp.tool()
@logged("schedule")
def current_block() -> dict | None:
    """지금 진행 중인 블록 (start <= now < end)."""
    now = _now()
    with connect() as c:
        acts = _activities_map(c)
        rows = c.execute(
            "SELECT * FROM blocks WHERE start_at <= ? AND completed_at IS NULL ORDER BY start_at DESC LIMIT 5",
            (now.isoformat(),),
        ).fetchall()
        for r in rows:
            start = dt.datetime.fromisoformat(r["start_at"])
            end = start + dt.timedelta(minutes=r["duration_min"])
            if start <= now < end:
                return _fmt_block(r, acts)
    return None


@mcp.tool()
@logged("schedule")
def complete_block(block_id: int, note: str | None = None) -> dict:
    """블록 완료 처리. 끝난 직후나 나중에 호출 가능."""
    with connect() as c:
        row = c.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()
        if not row:
            return {"error": f"no block {block_id}"}
        if row["completed_at"]:
            return {"error": f"block {block_id} already completed at {row['completed_at']}"}
        c.execute(
            "UPDATE blocks SET completed_at = ?, completion_note = ? WHERE id = ?",
            (_now().isoformat(), note, block_id),
        )
        row = c.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()
        start = dt.datetime.fromisoformat(row["start_at"])
        _write_daily_note(c, start.date().isoformat())
        _rewrite_calendars_for(c, [start.date().isoformat()])
        return _fmt_block(row, _activities_map(c))


@mcp.tool()
@logged("schedule")
def weekly_summary(weeks: int = 1) -> dict:
    """지난 N주 활동 시간 합계 (완료된 블록 기준)."""
    cutoff = _now() - dt.timedelta(weeks=weeks)
    with connect() as c:
        rows = c.execute(
            """
            SELECT activity, COUNT(*) as cnt, SUM(duration_min) as minutes
            FROM blocks
            WHERE completed_at IS NOT NULL AND start_at >= ?
            GROUP BY activity
            ORDER BY minutes DESC
            """,
            (cutoff.isoformat(),),
        ).fetchall()
        acts = _activities_map(c)
        return {
            "since": cutoff.date().isoformat(),
            "by_activity": [
                {
                    "activity": r["activity"],
                    "icon": acts.get(r["activity"], {}).get("icon", "•"),
                    "blocks": r["cnt"],
                    "minutes": r["minutes"],
                }
                for r in rows
            ],
            "total_minutes": sum(r["minutes"] for r in rows),
        }


# ---------- items (책/영화/시리즈/프로젝트 etc) ----------

def _fmt_item(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "icon": ITEM_KIND_ICON.get(row["kind"], "•"),
        "title": row["title"],
        "author_or_artist": row["author_or_artist"],
        "status": row["status"],
        "progress": row["progress"],
        "notes": row["notes"],
        "priority": row["priority"],
        "added_at": row["added_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


PLAN_VIEWS = [
    {
        "name": "reading",
        "icon": "📚",
        "title": "책",
        "kinds": ["book"],
        "labels": {"in_progress": "🟢 읽는 중", "backlog": "🟡 읽고 싶은", "paused": "⏸️ 잠시 멈춤", "done": "✅ 읽음", "abandoned": "❌ 포기"},
    },
    {
        "name": "watching",
        "icon": "🎬",
        "title": "영화·드라마·시리즈",
        "kinds": ["movie", "series"],
        "labels": {"in_progress": "🟢 보는 중", "backlog": "🟡 보고 싶은", "paused": "⏸️ 잠시 멈춤", "done": "✅ 다 봤음", "abandoned": "❌ 중단"},
    },
    {
        "name": "album",
        "icon": "💿",
        "title": "힙합 앨범 작업",
        "kinds": ["album"],
        "labels": {"in_progress": "🟢 작업 중", "backlog": "🟡 콘셉트·아이디어", "paused": "⏸️ 멈춤", "done": "✅ 발매", "abandoned": "❌ 폐기"},
    },
    {
        "name": "learning",
        "icon": "🎓",
        "title": "공부 중인 것",
        "kinds": ["course", "habit"],
        "labels": {"in_progress": "🟢 진행 중", "backlog": "🟡 시작하려는 중", "paused": "⏸️ 멈춤", "done": "✅ 마침", "abandoned": "❌ 폐기"},
    },
    {
        "name": "creating",
        "icon": "🛠️",
        "title": "만드는 것·기획",
        "kinds": ["project"],
        "labels": {"in_progress": "🟢 진행 중", "backlog": "🟡 백로그·아이디어", "paused": "⏸️ 멈춤", "done": "✅ 완료", "abandoned": "❌ 폐기"},
    },
    {
        "name": "other",
        "icon": "📋",
        "title": "기타",
        "kinds": "_default",
        "labels": {"in_progress": "🟢 진행 중", "backlog": "🟡 백로그", "paused": "⏸️ 멈춤", "done": "✅ 완료", "abandoned": "❌ 폐기"},
    },
]

_SPECIFIED_KINDS = {k for view in PLAN_VIEWS for k in (view["kinds"] if view["kinds"] != "_default" else [])}


def _write_plans(con):
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    for view in PLAN_VIEWS:
        if view["kinds"] == "_default":
            placeholders = ",".join("?" * len(_SPECIFIED_KINDS))
            rows = con.execute(
                f"SELECT * FROM items WHERE kind NOT IN ({placeholders}) ORDER BY status, priority DESC, added_at DESC",
                tuple(_SPECIFIED_KINDS),
            ).fetchall()
        else:
            placeholders = ",".join("?" * len(view["kinds"]))
            rows = con.execute(
                f"SELECT * FROM items WHERE kind IN ({placeholders}) ORDER BY status, priority DESC, added_at DESC",
                tuple(view["kinds"]),
            ).fetchall()
        by_status: dict[str, list] = {}
        for r in rows:
            by_status.setdefault(r["status"], []).append(r)
        lines = [
            "---",
            f"generated: {_now().isoformat(timespec='seconds')}",
            "---",
            "",
            f"# {view['icon']} {view['title']}",
            "",
        ]
        if not rows:
            lines.append("- (비어있음)")
            lines.append("")
        for status in ["in_progress", "backlog", "paused", "done", "abandoned"]:
            items = by_status.get(status, [])
            if not items:
                continue
            label = view["labels"].get(status, status)
            lines.append(f"## {label}")
            lines.append("")
            for it in items:
                title = it["title"]
                if it["author_or_artist"]:
                    title = f"{title} · {it['author_or_artist']}"
                bits = []
                if it["progress"]:
                    bits.append(it["progress"])
                if it["started_at"]:
                    bits.append(f"시작 {it['started_at'][:10]}")
                if it["finished_at"] and status == "done":
                    bits.append(f"완료 {it['finished_at'][:10]}")
                if it["priority"]:
                    bits.append(f"⭐{it['priority']}")
                line = f"- **{title}**"
                if bits:
                    line += " — " + ", ".join(bits)
                lines.append(line)
                if it["notes"]:
                    lines.append(f"    - {it['notes']}")
            lines.append("")
        path = PLANS_DIR / f"{view['name']}.md"
        path.write_text("\n".join(lines), encoding="utf-8")


def _write_items_note(con):
    rows = con.execute("SELECT * FROM items ORDER BY status, kind, priority DESC, added_at DESC").fetchall()
    SCHEDULE_DIR.mkdir(parents=True, exist_ok=True)
    path = SCHEDULE_DIR / "items.md"
    by_status: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        by_status.setdefault(r["status"], []).append(r)

    lines = [
        "---",
        f"generated: {_now().isoformat(timespec='seconds')}",
        "---",
        "",
        "# 📋 진행 중인 것들 + 백로그",
        "",
    ]

    def render_section(header: str, status: str):
        items = by_status.get(status, [])
        if not items:
            return
        lines.append(f"## {header}")
        lines.append("")
        by_kind: dict[str, list[sqlite3.Row]] = {}
        for it in items:
            by_kind.setdefault(it["kind"], []).append(it)
        for kind in sorted(by_kind):
            icon = ITEM_KIND_ICON.get(kind, "•")
            lines.append(f"### {icon} {kind}")
            for it in by_kind[kind]:
                title = it["title"]
                if it["author_or_artist"]:
                    title = f"{title} · {it['author_or_artist']}"
                line = f"- [ ] **{title}**"
                bits = []
                if it["progress"]:
                    bits.append(it["progress"])
                if it["started_at"]:
                    bits.append(f"시작 {it['started_at'][:10]}")
                if it["priority"]:
                    bits.append(f"⭐{it['priority']}")
                if bits:
                    line += f" — {', '.join(bits)}"
                if status == "done" and it["finished_at"]:
                    line = line.replace("[ ]", "[x]") + f" (완료 {it['finished_at'][:10]})"
                lines.append(line)
                if it["notes"]:
                    lines.append(f"    - {it['notes']}")
            lines.append("")

    render_section("🟢 진행 중 (in_progress)", "in_progress")
    render_section("🟡 백로그 (backlog)", "backlog")
    render_section("⏸️ 잠시 멈춤 (paused)", "paused")
    render_section("✅ 완료 (done)", "done")
    render_section("❌ 포기 (abandoned)", "abandoned")

    path.write_text("\n".join(lines), encoding="utf-8")


@mcp.tool()
@logged("schedule")
def add_item(
    kind: str,
    title: str,
    author_or_artist: str | None = None,
    status: str = "backlog",
    progress: str | None = None,
    notes: str | None = None,
    priority: int = 0,
) -> dict:
    """진행 중이거나 하고 싶은 것 추가 (책/영화/시리즈/앨범/프로젝트 등).

    kind: book/movie/series/album/podcast/project/habit/course/paper or 자유
    status: backlog (기본) | in_progress | paused | done | abandoned
    """
    if status not in ITEM_STATUSES:
        return {"error": f"unknown status. valid: {sorted(ITEM_STATUSES)}"}
    now = _now().isoformat(timespec="seconds")
    started_at = now if status == "in_progress" else None
    finished_at = now if status == "done" else None
    with connect() as c:
        cur = c.execute(
            """INSERT INTO items (kind, title, author_or_artist, status, progress, notes, priority,
                                  added_at, started_at, finished_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (kind, title, author_or_artist, status, progress, notes, priority, now, started_at, finished_at),
        )
        row = c.execute("SELECT * FROM items WHERE id = ?", (cur.lastrowid,)).fetchone()
        _write_items_note(c)
        _write_plans(c)
    return _fmt_item(row)


@mcp.tool()
@logged("schedule")
def update_item(
    item_id: int,
    title: str | None = None,
    status: str | None = None,
    progress: str | None = None,
    notes: str | None = None,
    priority: int | None = None,
) -> dict:
    """item의 제목·상태·진행도·메모·우선순위 갱신. status를 in_progress로 바꾸면 started_at 기록, done이면 finished_at."""
    with connect() as c:
        row = c.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return {"error": f"no item {item_id}"}
        fields = []
        params: list = []
        now = _now().isoformat(timespec="seconds")
        if title is not None:
            fields.append("title = ?")
            params.append(title)
        if status is not None:
            if status not in ITEM_STATUSES:
                return {"error": f"unknown status. valid: {sorted(ITEM_STATUSES)}"}
            fields.append("status = ?")
            params.append(status)
            if status == "in_progress" and not row["started_at"]:
                fields.append("started_at = ?")
                params.append(now)
            if status == "done":
                fields.append("finished_at = ?")
                params.append(now)
        if progress is not None:
            fields.append("progress = ?")
            params.append(progress)
        if notes is not None:
            fields.append("notes = ?")
            params.append(notes)
        if priority is not None:
            fields.append("priority = ?")
            params.append(priority)
        if not fields:
            return _fmt_item(row)
        params.append(item_id)
        c.execute(f"UPDATE items SET {', '.join(fields)} WHERE id = ?", params)
        row = c.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        _write_items_note(c)
        _write_plans(c)
    return _fmt_item(row)


@mcp.tool()
@logged("schedule")
def list_items(kind: str | None = None, status: str | None = None, limit: int = 100) -> list[dict]:
    """item 목록. kind나 status로 필터."""
    q = "SELECT * FROM items WHERE 1=1"
    params: list = []
    if kind:
        q += " AND kind = ?"
        params.append(kind)
    if status:
        q += " AND status = ?"
        params.append(status)
    q += " ORDER BY status, priority DESC, added_at DESC LIMIT ?"
    params.append(limit)
    with connect() as c:
        return [_fmt_item(r) for r in c.execute(q, params)]


@mcp.tool()
@logged("schedule")
def current_items() -> list[dict]:
    """지금 진행 중인 모든 것 (status=in_progress). '뭐 읽고 있지?' 같은 질문에."""
    return list_items(status="in_progress")


# ---------- commitments (약속·이벤트) ----------

def _fmt_commitment(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "when_at": row["when_at"],
        "duration_min": row["duration_min"],
        "where_at": row["where_at"],
        "with_whom": row["with_whom"],
        "notes": row["notes"],
        "status": row["status"],
        "added_at": row["added_at"],
    }


def _write_commitments_note(con):
    now_iso = _now().isoformat()
    rows = con.execute(
        "SELECT * FROM commitments ORDER BY when_at"
    ).fetchall()
    SCHEDULE_DIR.mkdir(parents=True, exist_ok=True)
    path = SCHEDULE_DIR / "commitments.md"

    upcoming = [r for r in rows if r["status"] == "upcoming" and r["when_at"] >= now_iso]
    past = [r for r in rows if r["status"] != "upcoming" or r["when_at"] < now_iso][-20:]

    lines = [
        "---",
        f"generated: {_now().isoformat(timespec='seconds')}",
        "---",
        "",
        "# 📅 약속·이벤트",
        "",
        "## 다가오는",
        "",
    ]
    if not upcoming:
        lines.append("- (없음)")
    for r in upcoming:
        when = dt.datetime.fromisoformat(r["when_at"])
        day = WEEKDAY_KR[when.weekday()]
        s = f"- **{when.strftime('%Y-%m-%d (')}{day}{when.strftime(') %H:%M')}** — {r['title']}"
        bits = []
        if r["with_whom"]:
            bits.append(f"with {r['with_whom']}")
        if r["where_at"]:
            bits.append(f"@ {r['where_at']}")
        if r["duration_min"]:
            bits.append(f"{r['duration_min']}분")
        if bits:
            s += f" ({', '.join(bits)})"
        lines.append(s)
        if r["notes"]:
            lines.append(f"    - {r['notes']}")
    lines.append("")
    lines.append("## 지난 / 처리됨")
    lines.append("")
    if not past:
        lines.append("- (없음)")
    for r in past:
        when = dt.datetime.fromisoformat(r["when_at"])
        status_icon = {"completed": "✓", "cancelled": "✗", "upcoming": "·"}.get(r["status"], "·")
        lines.append(f"- {status_icon} {when.strftime('%Y-%m-%d')} — {r['title']}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


@mcp.tool()
@logged("schedule")
def add_commitment(
    title: str,
    when: str,
    where: str | None = None,
    with_whom: str | None = None,
    duration_min: int | None = None,
    notes: str | None = None,
    category: str | None = None,
) -> dict:
    """약속·이벤트 등록.

    when: 'YYYY-MM-DD HH:MM' 또는 ISO. 시간 없는 통째 하루 이벤트는 'YYYY-MM-DD 00:00' 권장.
    category: class 🎓 / exam 📝 / presentation 🎤 / meeting 👥 / personal 📌 / travel 🚆 / other.
              생략 시 title에서 자동 추정.
    """
    when_dt = _parse_dt(when)
    now = _now().isoformat(timespec="seconds")
    cat = category if category in COMMITMENT_CATEGORIES else _auto_category(title)
    with connect() as c:
        cur = c.execute(
            """INSERT INTO commitments (title, when_at, duration_min, where_at, with_whom, notes, category, added_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, when_dt.isoformat(), duration_min, where, with_whom, notes, cat, now),
        )
        row = c.execute("SELECT * FROM commitments WHERE id = ?", (cur.lastrowid,)).fetchone()
        _write_commitments_note(c)
        _rewrite_calendars_for(c, [when_dt.date().isoformat()])
    return _fmt_commitment(row)


@mcp.tool()
@logged("schedule")
def update_commitment(
    commitment_id: int,
    title: str | None = None,
    when: str | None = None,
    where: str | None = None,
    with_whom: str | None = None,
    duration_min: int | None = None,
    notes: str | None = None,
) -> dict:
    """기존 약속의 필드를 갱신. None인 인자는 변경 안 함. notes는 새로 덮어씀(추가 X)."""
    with connect() as c:
        row = c.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
        if not row:
            return {"error": f"no commitment {commitment_id}"}
        old_date = dt.datetime.fromisoformat(row["when_at"]).date().isoformat()
        fields = []
        params: list = []
        new_date = old_date
        if title is not None:
            fields.append("title = ?"); params.append(title)
        if when is not None:
            when_dt = _parse_dt(when)
            fields.append("when_at = ?"); params.append(when_dt.isoformat())
            new_date = when_dt.date().isoformat()
        if where is not None:
            fields.append("where_at = ?"); params.append(where)
        if with_whom is not None:
            fields.append("with_whom = ?"); params.append(with_whom)
        if duration_min is not None:
            fields.append("duration_min = ?"); params.append(duration_min)
        if notes is not None:
            fields.append("notes = ?"); params.append(notes)
        if not fields:
            return _fmt_commitment(row)
        params.append(commitment_id)
        c.execute(f"UPDATE commitments SET {', '.join(fields)} WHERE id = ?", params)
        row = c.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
        _write_commitments_note(c)
        _rewrite_calendars_for(c, list({old_date, new_date}))
    return _fmt_commitment(row)


@mcp.tool()
@logged("schedule")
def list_commitments(upcoming_only: bool = True, days_ahead: int = 30) -> list[dict]:
    """약속 목록. 기본은 다가오는 30일 안."""
    now = _now()
    with connect() as c:
        if upcoming_only:
            cutoff = (now + dt.timedelta(days=days_ahead)).isoformat()
            rows = c.execute(
                "SELECT * FROM commitments WHERE status = 'upcoming' AND when_at >= ? AND when_at <= ? ORDER BY when_at",
                (now.isoformat(), cutoff),
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM commitments ORDER BY when_at DESC LIMIT 100").fetchall()
        return [_fmt_commitment(r) for r in rows]


@mcp.tool()
@logged("schedule")
def complete_commitment(commitment_id: int, notes: str | None = None) -> dict:
    """약속 완료 처리."""
    with connect() as c:
        row = c.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
        if not row:
            return {"error": f"no commitment {commitment_id}"}
        new_notes = row["notes"] or ""
        if notes:
            new_notes = (new_notes + "\n" + notes).strip()
        c.execute("UPDATE commitments SET status = 'completed', notes = ? WHERE id = ?", (new_notes, commitment_id))
        row = c.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
        _write_commitments_note(c)
        _rewrite_calendars_for(c, [dt.datetime.fromisoformat(row["when_at"]).date().isoformat()])
    return _fmt_commitment(row)


@mcp.tool()
@logged("schedule")
def cancel_commitment(commitment_id: int, reason: str | None = None) -> dict:
    """약속 취소."""
    with connect() as c:
        row = c.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
        if not row:
            return {"error": f"no commitment {commitment_id}"}
        new_notes = row["notes"] or ""
        if reason:
            new_notes = (new_notes + f"\n취소 사유: {reason}").strip()
        c.execute("UPDATE commitments SET status = 'cancelled', notes = ? WHERE id = ?", (new_notes, commitment_id))
        row = c.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
        _write_commitments_note(c)
        _rewrite_calendars_for(c, [dt.datetime.fromisoformat(row["when_at"]).date().isoformat()])
    return _fmt_commitment(row)


if __name__ == "__main__":
    mcp.run()
