#!/usr/bin/env python3
"""brain MCP server — Coin의 세컨드 브레인.

서희님이 읽은 책, 본 영화, 떠오른 생각, 나눈 대화, 마주친 인사이트를
옵시디언 Vault의 Brain/ 폴더로 정리해 저장한다. notion-sync가 30분마다
노션으로 미러링하므로 폰/다른 PC에서도 바로 조회 가능.

파일 위치: ~/Documents/Obsidian Vault/Brain/YYYY/MM/YYYY-MM-DD-{slug}.md
"""
import datetime as dt
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from usage_logger import logged

mcp = FastMCP("brain")

VAULT = Path.home() / "Documents" / "Obsidian Vault"
BRAIN = VAULT / "Brain"
JOURNAL = VAULT / "Journal"
SCHEDULE_DB = Path.home() / "openclaw-tools" / "data" / "schedule.db"
WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]

EXPENSE_SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  amount INTEGER NOT NULL,
  item TEXT NOT NULL,
  category TEXT,
  when_at TEXT NOT NULL,
  added_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_expenses_when ON expenses(when_at);
"""


def _ensure_expense_schema(con):
    con.executescript(EXPENSE_SCHEMA)
COMMITMENT_ICON = {
    "class": "🎓",
    "exam": "📝",
    "presentation": "🎤",
    "meeting": "👥",
    "travel": "🚆",
    "personal": "📌",
    "other": "•",
}

KINDS = {"book", "movie", "conversation", "thought", "insight", "lyric_idea", "research"}
KIND_ICON = {
    "book": "📚",
    "movie": "🎬",
    "conversation": "💬",
    "thought": "💭",
    "insight": "💡",
    "lyric_idea": "✍️",
    "research": "🔬",
}

KST = dt.timezone(dt.timedelta(hours=9))


def _now() -> dt.datetime:
    return dt.datetime.now(KST)


def _slugify(s: str, max_len: int = 40) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\s가-힣-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s)
    return s[:max_len] or "untitled"


def _path_for(kind: str, when: dt.datetime, slug: str) -> Path:
    return BRAIN / kind / f"{when.date().isoformat()}-{slug}.md"


def _ensure_dir(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)


def _parse_when(when: str | None) -> dt.datetime:
    if not when:
        return _now()
    try:
        d = dt.datetime.fromisoformat(when)
        if d.tzinfo is None:
            d = d.replace(tzinfo=KST)
        return d.astimezone(KST)
    except ValueError:
        return _now()


def _format_note(kind: str, title: str, content: str, tags: list[str], when: dt.datetime) -> str:
    icon = KIND_ICON.get(kind, "📝")
    tag_str = ", ".join(tags) if tags else ""
    lines = [
        "---",
        f"date: {when.date().isoformat()}",
        f"kind: {kind}",
        f"title: {title}",
        f"tags: [{tag_str}]",
        f"created: {when.isoformat(timespec='seconds')}",
        "---",
        "",
        f"# {icon} {title}",
        "",
        content.strip(),
        "",
    ]
    return "\n".join(lines)


# ---------- Tools ----------

@mcp.tool()
@logged("brain")
def note(
    kind: str,
    content: str,
    title: str | None = None,
    tags: list[str] | None = None,
    when: str | None = None,
) -> dict:
    """책/영화/대화/생각/인사이트/가사아이디어/연구 메모를 Brain 폴더에 저장.

    kind: book | movie | conversation | thought | insight | lyric_idea | research
    content: 본문 (마크다운)
    title: 제목 (없으면 본문 첫 줄에서 생성)
    tags: 태그 리스트
    when: ISO 시간 (기본: 지금)
    """
    if kind not in KINDS:
        return {"error": f"unknown kind '{kind}'. valid: {sorted(KINDS)}"}
    w = _parse_when(when)
    if not title:
        first_line = content.strip().splitlines()[0] if content.strip() else "untitled"
        title = first_line[:60].strip()
    slug = _slugify(title)
    path = _path_for(kind, w, slug)
    if path.exists():
        suffix = w.strftime("%H%M")
        path = path.with_name(f"{path.stem}-{suffix}{path.suffix}")
    _ensure_dir(path)
    body = _format_note(kind, title, content, tags or [], w)
    path.write_text(body, encoding="utf-8")
    return {
        "ok": True,
        "path": str(path.relative_to(VAULT)),
        "kind": kind,
        "title": title,
        "tags": tags or [],
    }


@mcp.tool()
@logged("brain")
def recent_notes(days: int = 7, kind: str | None = None, limit: int = 50) -> list[dict]:
    """최근 N일 안의 Brain 노트 목록. kind로 필터 가능."""
    if not BRAIN.exists():
        return []
    cutoff = _now() - dt.timedelta(days=days)
    results = []
    for md in BRAIN.rglob("*.md"):
        try:
            mtime = dt.datetime.fromtimestamp(md.stat().st_mtime, tz=KST)
        except OSError:
            continue
        if mtime < cutoff:
            continue
        meta = _read_front_matter(md)
        if kind and meta.get("kind") != kind:
            continue
        results.append({
            "path": str(md.relative_to(VAULT)),
            "kind": meta.get("kind", "unknown"),
            "title": meta.get("title", md.stem),
            "tags": meta.get("tags", []),
            "date": meta.get("date") or mtime.date().isoformat(),
        })
    results.sort(key=lambda x: x["date"], reverse=True)
    return results[:limit]


@mcp.tool()
@logged("brain")
def search_notes(query: str, limit: int = 20) -> list[dict]:
    """제목·본문·태그에서 키워드 검색 (대소문자 무시)."""
    if not BRAIN.exists() or not query.strip():
        return []
    q = query.lower()
    results = []
    for md in BRAIN.rglob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        if q not in text.lower():
            continue
        meta = _read_front_matter(md)
        idx = text.lower().find(q)
        snippet = text[max(0, idx - 40): idx + len(q) + 60].replace("\n", " ")
        results.append({
            "path": str(md.relative_to(VAULT)),
            "title": meta.get("title", md.stem),
            "kind": meta.get("kind", "unknown"),
            "snippet": snippet,
        })
    return results[:limit]


@mcp.tool()
@logged("brain")
def read_note(path: str) -> dict:
    """Vault 기준 상대 경로로 노트 전체 본문 반환."""
    full = VAULT / path
    try:
        full.resolve().relative_to(VAULT.resolve())
    except ValueError:
        return {"error": "path escapes vault"}
    if not full.exists():
        return {"error": "not found"}
    return {"path": path, "content": full.read_text(encoding="utf-8")}


@mcp.tool()
@logged("brain")
def log(content: str, when: str | None = None, tags: list[str] | None = None) -> dict:
    """그날 한 일·먹은 것·만난 사람·짧은 사건을 Journal/YYYY-MM-DD.md에 timestamp 찍어 append.

    `note`와 다른 점: note는 정리된 메모(책·영화·생각·인사이트), log는 raw 일상 기록.
    when 생략 시 지금. 한 호출 = 한 줄. 여러 항목은 여러 번 호출.
    """
    w = _parse_when(when)
    JOURNAL.mkdir(parents=True, exist_ok=True)
    path = JOURNAL / f"{w.date().isoformat()}.md"
    if not path.exists():
        weekday = WEEKDAY_KR[w.weekday()]
        header = f"# 🗓 {w.date().isoformat()} ({weekday})\n\n"
        path.write_text(header, encoding="utf-8")
    entry = f"- {content}"
    if tags:
        entry += "  " + " ".join(f"#{t}" for t in tags)
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry + "\n")
    return {"ok": True, "path": str(path.relative_to(VAULT)), "entry": entry}


@mcp.tool()
@logged("brain")
def log_expense(amount: int, item: str, category: str | None = None, when: str | None = None) -> dict:
    """지출 한 건 기록. DB에 저장 + Journal에 💸 entry로 append.

    amount: 원 단위 정수 (예: 8000)
    item: 무엇 (예: "점심 — 김치찌개")
    category: 밥/카페/교통/책/장비/구독/엔터/기타 등 자유 분류
    when: ISO 또는 'HH:MM' 또는 'YYYY-MM-DD HH:MM' (생략 시 지금)
    """
    w = _parse_when(when)
    now = _now().isoformat(timespec="seconds")
    with sqlite3.connect(SCHEDULE_DB) as con:
        _ensure_expense_schema(con)
        con.execute(
            "INSERT INTO expenses (amount, item, category, when_at, added_at) VALUES (?, ?, ?, ?, ?)",
            (amount, item, category, w.isoformat(), now),
        )
        con.commit()
    # Append to Journal
    JOURNAL.mkdir(parents=True, exist_ok=True)
    path = JOURNAL / f"{w.date().isoformat()}.md"
    if not path.exists():
        weekday = WEEKDAY_KR[w.weekday()]
        path.write_text(f"# 🗓 {w.date().isoformat()} ({weekday})\n\n", encoding="utf-8")
    cat_tag = f"  #{category}" if category else ""
    entry = f"- 💸 {item} ({amount:,}원){cat_tag}"
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry + "\n")
    return {"ok": True, "amount": amount, "item": item, "category": category,
            "when": w.isoformat(), "path": str(path.relative_to(VAULT))}


@mcp.tool()
@logged("brain")
def day_expenses(date: str | None = None) -> dict:
    """그날의 지출 목록 + 합계."""
    d = dt.date.fromisoformat(date) if date else _now().date()
    with sqlite3.connect(SCHEDULE_DB) as con:
        _ensure_expense_schema(con)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM expenses WHERE date(when_at) = ? ORDER BY when_at",
            (d.isoformat(),),
        ).fetchall()
    items = [{"amount": r["amount"], "item": r["item"], "category": r["category"],
              "when": r["when_at"]} for r in rows]
    by_cat: dict[str, int] = {}
    for r in rows:
        cat = r["category"] or "기타"
        by_cat[cat] = by_cat.get(cat, 0) + r["amount"]
    total = sum(r["amount"] for r in rows)
    return {"date": d.isoformat(), "items": items, "by_category": by_cat, "total": total}


@mcp.tool()
@logged("brain")
def finalize_day(date: str | None = None) -> dict:
    """그날 Journal에 '💰 지출 합계' 섹션을 추가/갱신. 기존 섹션이 있으면 덮어씀.

    date 생략 시 어제 (매일 자정 자동 호출에 적합).
    """
    if date:
        d = dt.date.fromisoformat(date)
    else:
        d = (_now() - dt.timedelta(days=1)).date()
    path = JOURNAL / f"{d.isoformat()}.md"
    summary = day_expenses(d.isoformat())
    if not path.exists():
        if not summary["items"]:
            return {"date": d.isoformat(), "skipped": "no journal, no expenses"}
        weekday = WEEKDAY_KR[d.weekday()]
        path.write_text(f"# 🗓 {d.isoformat()} ({weekday})\n\n", encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    # remove existing total section
    marker = "\n## 💰 지출 합계\n"
    if marker in text:
        before = text.split(marker)[0].rstrip() + "\n"
        text = before
    if summary["items"]:
        lines = [text.rstrip(), "", "## 💰 지출 합계", ""]
        for cat, amt in sorted(summary["by_category"].items(), key=lambda x: -x[1]):
            lines.append(f"- {cat}: {amt:,}원")
        lines.append("")
        lines.append(f"**총 {summary['total']:,}원** · {len(summary['items'])}건")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
    else:
        # no expenses; ensure no stale section
        path.write_text(text, encoding="utf-8")
    return {"date": d.isoformat(), "total": summary["total"], "count": len(summary["items"]),
            "path": str(path.relative_to(VAULT))}


@mcp.tool()
@logged("brain")
def log_day_commitments(date: str | None = None, include_future: bool = False) -> dict:
    """그날 commitments(수업·발표·시험·미팅·이동·약속)를 Journal/YYYY-MM-DD.md에 시간별로 자동 기록.

    이미 기록된 entry는 중복 안 함. include_future=False면 이미 시작 시간이 지난 것만 기록.
    date 생략 시 오늘.
    """
    d = dt.date.fromisoformat(date) if date else _now().date()
    JOURNAL.mkdir(parents=True, exist_ok=True)
    path = JOURNAL / f"{d.isoformat()}.md"
    if not path.exists():
        weekday = WEEKDAY_KR[d.weekday()]
        path.write_text(f"# 🗓 {d.isoformat()} ({weekday})\n\n", encoding="utf-8")
    now_iso = _now().isoformat()
    query = (
        "SELECT title, when_at, category FROM commitments "
        "WHERE date(when_at) = ? AND status = 'upcoming'"
    )
    params: list = [d.isoformat()]
    if not include_future:
        query += " AND when_at <= ?"
        params.append(now_iso)
    query += " ORDER BY when_at"
    with sqlite3.connect(SCHEDULE_DB) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(query, params).fetchall()
    existing = path.read_text(encoding="utf-8")
    added = []
    for r in rows:
        icon = COMMITMENT_ICON.get(r["category"] or "other", "•")
        entry = f"- {icon} {r['title']}"
        if entry in existing:
            continue
        added.append(entry)
    if added:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(added) + "\n")
    return {"date": d.isoformat(), "added": added, "count": len(added), "path": str(path.relative_to(VAULT))}


@mcp.tool()
@logged("brain")
def recent_logs(days: int = 7, limit: int = 30) -> list[dict]:
    """최근 N일의 Journal 로그 — 각 날짜의 실제 내용(불릿)을 함께 반환."""
    if not JOURNAL.exists():
        return []
    cutoff = (_now() - dt.timedelta(days=days)).date()
    out = []
    for md in sorted(JOURNAL.glob("*.md"), reverse=True):
        try:
            file_date = dt.date.fromisoformat(md.stem)
        except ValueError:
            continue
        if file_date < cutoff:
            continue
        text = md.read_text(encoding="utf-8")
        # 불릿 줄("- ..." / "* ...", 들여쓰기 포함) = 실제 기록
        bullets = [ln.strip() for ln in text.splitlines() if ln.lstrip().startswith(("- ", "* "))]
        out.append({
            "path": str(md.relative_to(VAULT)),
            "date": file_date.isoformat(),
            "entries": len(bullets),
            "content": "\n".join(bullets),
        })
        if len(out) >= limit:
            break
    return out


@mcp.tool()
@logged("brain")
def vault_list(folder: str = "", limit: int = 200) -> list[dict]:
    """Vault 안 마크다운 파일 목록 (Brain 외 다른 폴더도 가능: '가사', 'Daily', '아이디어' 등)."""
    base = (VAULT / folder).resolve()
    try:
        base.relative_to(VAULT.resolve())
    except ValueError:
        return [{"error": "path escapes vault"}]
    if not base.exists() or not base.is_dir():
        return []
    out = []
    for md in sorted(base.rglob("*.md")):
        try:
            mtime = dt.datetime.fromtimestamp(md.stat().st_mtime, tz=KST)
        except OSError:
            continue
        out.append({
            "path": str(md.relative_to(VAULT)),
            "modified": mtime.isoformat(timespec="seconds"),
        })
    return out[:limit]


@mcp.tool()
@logged("brain")
def vault_search(query: str, folder: str = "", limit: int = 30) -> list[dict]:
    """Vault 전체 (또는 특정 폴더) 마크다운에서 키워드 검색. Brain·가사·Daily·아이디어 등 다 포함."""
    if not query.strip():
        return []
    base = (VAULT / folder).resolve()
    try:
        base.relative_to(VAULT.resolve())
    except ValueError:
        return [{"error": "path escapes vault"}]
    if not base.exists():
        return []
    q = query.lower()
    results = []
    for md in base.rglob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        if q not in text.lower():
            continue
        idx = text.lower().find(q)
        snippet = text[max(0, idx - 40): idx + len(q) + 80].replace("\n", " ")
        results.append({
            "path": str(md.relative_to(VAULT)),
            "snippet": snippet,
        })
    return results[:limit]


# ---------- helpers ----------

def _read_front_matter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    meta: dict = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [t.strip() for t in v[1:-1].split(",") if t.strip()]
        meta[k.strip()] = v
    return meta


@mcp.tool()
@logged("brain")
def save_review(content: str, date: str | None = None) -> dict:
    """주간 리뷰(또는 임의의 리뷰 문서)를 Vault의 Reviews/ 폴더에 저장.

    content: 리뷰 본문 (마크다운). front matter 없이 본문만 주면 됨.
    date: 리뷰 날짜 ISO (YYYY-MM-DD, 기본: 오늘). 파일명 = Reviews/{date}.md
    같은 날짜 파일이 있으면 덮어쓴다.
    notion-sync가 30분마다 미러링하므로 폰/웹에서도 조회 가능.
    """
    w = _parse_when(date)
    d = w.date().isoformat()
    reviews = VAULT / "Reviews"
    path = reviews / f"{d}.md"
    _ensure_dir(path)
    body = content if content.lstrip().startswith("---") else (
        f"---\ndate: {d}\ntype: weekly-review\ngenerated_by: AI Planner\n---\n\n{content.strip()}\n"
    )
    path.write_text(body, encoding="utf-8")
    return {"ok": True, "path": str(path.relative_to(VAULT)), "date": d}


if __name__ == "__main__":
    mcp.run()
