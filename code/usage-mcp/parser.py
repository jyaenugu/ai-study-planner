"""Parse Claude session .jsonl files and aggregate token usage."""
import datetime as dt
import glob
import json
from collections import defaultdict
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
RATES_PATH = Path(__file__).parent / "rates.json"


def _rates() -> dict:
    return json.loads(RATES_PATH.read_text())


def _iter_session_files():
    yield from glob.glob(str(PROJECTS_DIR / "**" / "*.jsonl"), recursive=True)


def iter_messages():
    """Yield {date, model, in, out, cache_r, cache_5m, cache_1h, session_id, ts} for each assistant turn."""
    for path in _iter_session_files():
        sid = Path(path).stem
        try:
            with open(path) as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") != "assistant":
                        continue
                    # Only count OpenClaw-spawned Claude sessions, not standalone Claude Code.
                    # OpenClaw sets entrypoint=sdk-cli (vs cli for Claude Code).
                    if d.get("entrypoint") != "sdk-cli":
                        continue
                    msg = d.get("message", {})
                    usage = msg.get("usage")
                    if not usage:
                        continue
                    ts = d.get("timestamp")
                    if not ts:
                        continue
                    model = msg.get("model", "unknown")
                    if model.startswith("<") or model == "unknown":
                        continue
                    cc = usage.get("cache_creation") or {}
                    yield {
                        "date": ts[:10],
                        "model": model,
                        "in": usage.get("input_tokens", 0),
                        "out": usage.get("output_tokens", 0),
                        "cache_r": usage.get("cache_read_input_tokens", 0),
                        "cache_5m": cc.get("ephemeral_5m_input_tokens", 0),
                        "cache_1h": cc.get("ephemeral_1h_input_tokens", 0),
                        "session_id": sid,
                        "ts": ts,
                    }
        except OSError:
            continue


def cost_for(model: str, m: dict) -> float:
    rates = _rates().get(model)
    if not rates:
        return 0.0
    return (
        m["in"] * rates["input"]
        + m["out"] * rates["output"]
        + m["cache_r"] * rates["cache_read"]
        + m["cache_5m"] * rates["cache_5m"]
        + m["cache_1h"] * rates["cache_1h"]
    ) / 1_000_000


def aggregate(date_filter=None):
    """Group messages by (date, model). Returns dict[(date, model)] = totals + cost."""
    agg = defaultdict(lambda: {"in": 0, "out": 0, "cache_r": 0, "cache_5m": 0, "cache_1h": 0, "calls": 0})
    for m in iter_messages():
        if date_filter and not date_filter(m["date"]):
            continue
        key = (m["date"], m["model"])
        for k in ("in", "out", "cache_r", "cache_5m", "cache_1h"):
            agg[key][k] += m[k]
        agg[key]["calls"] += 1
    out = {}
    for (date, model), totals in agg.items():
        totals["cost_usd"] = cost_for(model, totals)
        out[(date, model)] = totals
    return out


def count_user_messages(date_filter=None) -> dict:
    """Returns dict[date] = number of user-sent messages in OpenClaw sessions."""
    counts = defaultdict(int)
    for path in _iter_session_files():
        try:
            with open(path) as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") != "user":
                        continue
                    if d.get("entrypoint") != "sdk-cli":
                        continue
                    ts = d.get("timestamp")
                    if not ts:
                        continue
                    date = ts[:10]
                    if date_filter and not date_filter(date):
                        continue
                    counts[date] += 1
        except OSError:
            continue
    return dict(counts)


def session_durations(date_filter=None) -> dict:
    """Returns dict[date] = total seconds spanned by sessions on that date (active time, capped per gap)."""
    by_session_date = defaultdict(list)
    for m in iter_messages():
        if date_filter and not date_filter(m["date"]):
            continue
        try:
            t = dt.datetime.fromisoformat(m["ts"].replace("Z", "+00:00"))
        except ValueError:
            continue
        by_session_date[(m["session_id"], m["date"])].append(t)
    out = defaultdict(float)
    for (sid, date), times in by_session_date.items():
        times.sort()
        # Sum gaps, capping each gap at 5 minutes (idle filter)
        total = 0.0
        for a, b in zip(times, times[1:]):
            gap = (b - a).total_seconds()
            total += min(gap, 300)
        out[date] += total
    return dict(out)
