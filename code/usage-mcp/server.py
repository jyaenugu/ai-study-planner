#!/usr/bin/env python3
"""openclaw-usage MCP. Tools to query token/cost/time spent across Claude sessions."""
import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from mcp.server.fastmcp import FastMCP
from parser import aggregate, count_user_messages, session_durations
from usage_logger import logged

mcp = FastMCP("openclaw-usage")


def _fmt_seconds(s: float) -> str:
    if s < 60:
        return f"{s:.0f}s"
    m = s / 60
    if m < 60:
        return f"{m:.0f}m"
    return f"{m / 60:.1f}h"


def _day_report(date: str) -> dict:
    agg = aggregate(date_filter=lambda d: d == date)
    durations = session_durations(date_filter=lambda d: d == date)
    by_model = {}
    total = {"in": 0, "out": 0, "cache_r": 0, "cache_5m": 0, "cache_1h": 0, "calls": 0, "cost_usd": 0.0}
    for (_, model), t in agg.items():
        by_model[model] = {
            "calls": t["calls"],
            "input_tokens": t["in"],
            "output_tokens": t["out"],
            "cache_read_tokens": t["cache_r"],
            "cache_create_5m_tokens": t["cache_5m"],
            "cache_create_1h_tokens": t["cache_1h"],
            "cost_usd": round(t["cost_usd"], 4),
        }
        for k in ("in", "out", "cache_r", "cache_5m", "cache_1h", "calls"):
            total[k] += t[k]
        total["cost_usd"] += t["cost_usd"]
    msg_counts = count_user_messages(date_filter=lambda d: d == date)
    return {
        "date": date,
        "chat_time": _fmt_seconds(durations.get(date, 0)),
        "messages_sent": msg_counts.get(date, 0),
        "bot_responses": total["calls"],
        "total_cost_usd": round(total["cost_usd"], 4),
        "input_tokens": total["in"],
        "output_tokens": total["out"],
        "cache_read_tokens": total["cache_r"],
        "by_model": by_model,
    }


@mcp.tool()
@logged("openclaw-usage")
def usage_today() -> dict:
    """오늘 사용량 (토큰·비용·활성 시간·모델별 breakdown)."""
    return _day_report(dt.date.today().isoformat())


@mcp.tool()
@logged("openclaw-usage")
def usage_day(date: str) -> dict:
    """특정 날짜(YYYY-MM-DD) 사용량."""
    return _day_report(date)


@mcp.tool()
@logged("openclaw-usage")
def usage_summary(days: int = 7) -> dict:
    """최근 N일 요약. 일별 합계 + 기간 총합."""
    end = dt.date.today()
    start = end - dt.timedelta(days=days - 1)
    in_range = lambda d: start.isoformat() <= d <= end.isoformat()
    agg = aggregate(date_filter=in_range)
    durations = session_durations(date_filter=in_range)
    msg_counts = count_user_messages(date_filter=in_range)
    daily = defaultdict(lambda: {"cost": 0.0, "calls": 0})
    for (date, _model), t in agg.items():
        daily[date]["cost"] += t["cost_usd"]
        daily[date]["calls"] += t["calls"]
    days_out = []
    for i in range(days):
        d = (start + dt.timedelta(days=i)).isoformat()
        info = daily.get(d, {"cost": 0.0, "calls": 0})
        days_out.append({
            "date": d,
            "chat_time": _fmt_seconds(durations.get(d, 0)),
            "messages_sent": msg_counts.get(d, 0),
            "bot_responses": info["calls"],
            "cost_usd": round(info["cost"], 4),
        })
    return {
        "range": f"{start} → {end}",
        "total_messages_sent": sum(d["messages_sent"] for d in days_out),
        "total_chat_seconds": sum(durations.get(d["date"], 0) for d in days_out),
        "total_cost_usd": round(sum(d["cost_usd"] for d in days_out), 4),
        "daily": days_out,
    }


@mcp.tool()
@logged("openclaw-usage")
def usage_by_model(date: str | None = None) -> dict:
    """특정 날짜(또는 오늘) 모델별 breakdown."""
    d = date or dt.date.today().isoformat()
    return {"date": d, "by_model": _day_report(d)["by_model"]}


@mcp.tool()
@logged("openclaw-usage")
def heatmap_generate() -> dict:
    """사용량 잔디밭 SVG를 Obsidian vault에 생성."""
    from heatmap import generate
    return {"ok": True, "path": str(generate())}


if __name__ == "__main__":
    mcp.run()
