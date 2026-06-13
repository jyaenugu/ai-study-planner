#!/usr/bin/env python3
"""Daily Journal finalizer — runs at 00:10 KST.

Adds '💰 지출 합계' section to yesterday's Journal/YYYY-MM-DD.md.
Pure SQLite + file I/O, no LLM. Imports the brain MCP module to reuse logic.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "openclaw-tools" / "brain-mcp"))
sys.path.insert(0, str(Path.home() / "openclaw-tools"))

import server as brain

if __name__ == "__main__":
    r = brain.finalize_day()
    print(r)
