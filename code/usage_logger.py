"""Append-only usage logger for MCP-mediated calls. Used by custom MCP servers."""
import datetime as dt
import fcntl
import functools
import os
import re
import time
from pathlib import Path

LOG_PATH = Path.home() / "USAGE_LOG.md"


def _channel() -> str:
    """TG if running inside OpenClaw-spawned Claude (env marker present), else CLI."""
    return "TG" if os.environ.get("OPENCLAW_SERVICE_MARKER") else "CLI"


def _summarize_args(kwargs: dict) -> str:
    if not kwargs:
        return ""
    parts = []
    for k, v in kwargs.items():
        s = repr(v) if not isinstance(v, str) else f'"{v}"'
        if len(s) > 30:
            s = s[:27] + "..."
        parts.append(f"{k}={s}")
    return f"({', '.join(parts)})"


def _summarize_result(result, max_len: int = 60) -> str:
    s = str(result)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[: max_len - 3] + "..."
    return s


def _day_number(text: str, today: str) -> int:
    """How many distinct date sections already exist? +1 if today is new."""
    dates = set(re.findall(r"^## (\d{4}-\d{2}-\d{2})", text, flags=re.M))
    if today in dates:
        return -1  # signal: section already exists
    return len(dates) + 1


def _append(line: str):
    """Append one entry line to USAGE_LOG.md under today's date section (creating it if needed)."""
    today = dt.date.today().isoformat()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            text = f.read()
            if not text.strip():
                # Initialize with header
                f.write(
                    "# USAGE_LOG — MCP-mediated calls\n\n"
                    "Format: `- HH:MM CHANNEL server task (OUTCOME, latency)`\n"
                    "Channels: `CLI` (openclaw terminal chat) | `TG` (Telegram bot)\n"
                    "Outcomes: `OK` | `CONFIRM` (user approved) | `FAILED` (with one-line cause)\n\n"
                    "---\n\n"
                )
                text = ""
            n = _day_number(text, today)
            if n != -1:
                # Need a new date section
                if not text.endswith("\n\n"):
                    f.write("\n" if text.endswith("\n") else "\n\n")
                f.write(f"## {today} (Day {n})\n")
            f.write(line + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def log_call(server: str, tool: str, kwargs: dict, outcome: str, latency_s: float, task_desc: str = ""):
    """Write one log line. task_desc overrides args summary if provided."""
    ts = dt.datetime.now().strftime("%H:%M")
    ch = _channel()
    desc = task_desc or f"{tool}{_summarize_args(kwargs)}"
    lat = f"~{latency_s:.0f}s" if latency_s >= 1 else f"~{int(latency_s * 1000)}ms"
    line = f"- {ts} {ch} {server} {desc} ({outcome}, {lat})"
    _append(line)


def logged(server: str):
    """Decorator that times a tool call and appends a USAGE_LOG entry. Use ABOVE @mcp.tool()."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            t0 = time.time()
            try:
                result = func(*args, **kwargs)
                summary = _summarize_result(result)
                desc = f"{func.__name__}{_summarize_args(kwargs)} → {summary}"
                log_call(server, func.__name__, kwargs, "OK", time.time() - t0, task_desc=desc)
                return result
            except Exception as e:
                msg = str(e).splitlines()[0] if str(e) else type(e).__name__
                if len(msg) > 50:
                    msg = msg[:47] + "..."
                log_call(server, func.__name__, kwargs, f"FAILED -- {msg}", time.time() - t0)
                raise
        return wrapper
    return decorator
