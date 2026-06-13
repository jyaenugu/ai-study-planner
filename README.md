# Coin — An AI Study Planner for Grad Students

> A private, daily-use **Personal AI Butler** that lives on my own laptop,
> remembers my research goals, logs my days, and gives me a grounded
> **weekly research review** — all driven through Telegram.

| | |
|---|---|
| **Class** | Generative AI and Blockchain (GIST) |
| **Author** | Seohee Han (한서희) — solo, 1 person |
| **Project type** | (i) Personal AI Butler |
| **Platform** | OpenClaw + Claude API + MCP, running as a `systemd` service on Ubuntu 24.04 |
| **Target user** | A graduate student (me) who needs a private, daily yardstick that research no longer provides |

### Deliverables

| Item | Location |
|---|---|
| Code | [`code/`](code/) |
| Paper / report | [`paper/report.md`](paper/report.md) |
| Slides | [`slides/AI-Study-Planner.pdf`](slides/AI-Study-Planner.pdf) |
| 7-day usage log | [`usage-log/USAGE_LOG.md`](usage-log/USAGE_LOG.md) |
| Demo video (≤ 5 min) | [`demo-video/`](demo-video/) — _link added after recording_ |

---

## 1. The problem

Grad school removed the one thing undergrad always gave me: **a yardstick.**
Exams are over, research has no score, and the weekly lab meeting is too coarse
to tell me whether *this* week actually went okay. Paper planners are tedious
and built for exam students. General chatbots don't know me — they have no
memory of my goals, so they hand back plausible-sounding generalities and
nothing accumulates.

**Coin** is my answer: a planner that remembers me and gives weekly feedback
that is *grounded in my own records* — not invented.

## 2. What it is

Coin is **Claude** wired into my real tools through **MCP (Model Context
Protocol)** and reachable from **Telegram**. I talk to it the way I'd text a
person; it reads and writes my Obsidian notes, tracks commitments, and once a
week writes a review that cites what I actually did.

```
                          ┌─────────────────┐
        Telegram  ───────▶│                 │◀──────  Obsidian Vault (notes)
        (chat UI)         │   OpenClaw      │
                          │   gateway        │◀──────  Notion (mobile mirror)
   Claude API  ──────────▶│   = "Coin"       │
   (Sonnet / Haiku)       │   built on MCP   │───────▶ Jekyll blog (GitHub Pages)
                          │                 │◀──────  Spotify (listening log)
                          └─────────────────┘
                                   │
                                fetch (web)
```

Runs on an LG gram 16 (i7-1195G7, 16 GB RAM, Ubuntu 24.04). The OpenClaw
gateway runs continuously as a `systemd` service, so Coin is always reachable.

## 3. MCP servers

Five local MCP servers expose my tools to Claude. Secrets never live in this
repo — each server reads its credentials from `~/.openclaw/*.json` at runtime.

| Server | Tools | What it does |
|---|---|---|
| `brain` | ~13 | Read/search/write my Obsidian Vault (journal, Brain notes, reviews) |
| `schedule` | ~17 | Calendar, todos, commitments, `weekly_summary` |
| `spotify` | ~15 | Listening log, "obsessed-on" tracks, playback, heatmap |
| `blog` | 6 | Publish posts/news to my Jekyll GitHub Pages blog |
| `usage` | 5 | Token/cost/time tracking from Claude session files |
| `fetch` | — | Read-only web access (`uvx mcp-server-fetch`) |

## 4. The core feature — a weekly review grounded in my notes (RAG)

This is the one thing a generic chatbot **cannot** do, because it doesn't have
my records:

```
My notes ──▶ retrieve ──▶ Claude Sonnet ──▶ weekly review
(Obsidian)   via brain     grounded answer    saved back to Vault
             MCP
```

Retrieval pulls three things before a single word is generated:

1. `brain.recent_logs(7)` → this week's 7 journal entries
2. `brain.read_note("RESEARCH_GOALS")` → my goal file
3. `schedule.weekly_summary` → this week's activity mix

Claude then writes the review **grounded in that retrieved context** — so the
feedback says "you finished the DAE paper" and "you slept at 5 AM" because it
*read* that, not because it guessed it. That is RAG (Retrieval-Augmented
Generation): retrieve first, then generate grounded in it. MCP is the pipe;
RAG pulls my data through it to write the answer.

## 5. Install & run

**Prerequisites:** Ubuntu (tested on 24.04), Python 3.12, [`uv`](https://github.com/astral-sh/uv),
an [OpenClaw](https://openclaw.ai) install, a Telegram bot token, and an
Anthropic API key. Spotify and Notion integrations are optional.

```bash
# 1. Clone
git clone <this-repo> && cd ai-study-planner/code

# 2. Create the shared venv and install dependencies
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Put your secrets in ~/.openclaw/ (NOT in this repo):
#    ~/.openclaw/openclaw.json   -> Anthropic API key, Telegram bot token
#    ~/.openclaw/notion.json     -> { "token": "...", "parent_page_id": "..." }
#    ~/.openclaw/spotify.json    -> Spotify OAuth (run hiphop-mcp/auth.py once)

# 4. Register the MCP servers in ~/.openclaw/openclaw.json, e.g.:
#    "mcp": { "servers": {
#       "brain":    { "command": ".../.venv/bin/python", "args": [".../brain-mcp/server.py"] },
#       "schedule": { "command": ".../.venv/bin/python", "args": [".../schedule-mcp/server.py"] },
#       "spotify":  { "command": ".../.venv/bin/python", "args": [".../hiphop-mcp/server.py"] },
#       "blog":     { "command": ".../.venv/bin/python", "args": [".../blog-mcp/server.py"] },
#       "fetch":    { "command": ".../uvx", "args": ["mcp-server-fetch"] }
#    }}

# 5. Start the gateway (it runs as a systemd service)
openclaw gateway        # then message your Telegram bot
```

Once running, message the Telegram bot — e.g. *"이번 주 리뷰 써줘"* (write this
week's review) — and Coin retrieves your week and replies.

## 6. Why not just use ChatGPT / Gemini? (differentiation)

A Big-Tech chatbot is a stateless stranger; **Coin is mine.** It runs on *my*
laptop, so my journal, research goals, and spending never leave the machine —
the cloud only ever sees the minimal slice of context a single request needs.
It is **grounded in my own Obsidian notes via RAG**, so its weekly feedback
cites what I actually did instead of inventing plausible generalities, and
those notes **accumulate** into a record that makes next week's review smarter.
It is **extensible through MCP** — five servers I wrote myself wire Claude into
Obsidian, Notion, Spotify, my blog, and the web — and it is **cost-controlled**:
a two-tier model stack (cheap Haiku for everyday calls, Sonnet only for the
weekly synthesis) plus a trimmed tool/context budget keep it under the API rate
limit and affordable to run every single day. None of those five things —
local-private, note-grounded, accumulating, self-extensible, cost-bounded — is
something a hosted chatbot gives me.

## 7. Engineering notes

- **Rate limit (API Tier-1: 30k input tokens/min).** Naively, the agent
  re-sends the whole conversation *plus* the manuals for all ~50 tools on every
  step — even "read one note" blows past 30k. Fix: `toolsAllow` (expose only
  the ~6 tools a weekly review needs), `lightContext` (trim persona/background
  to the minimum), and model choice (Sonnet only for the weekly synthesis).
  Result: fits under 30k, errors gone, cost down.
- **Cost economy.** It's an API, not a subscription — every action costs money.
  So the design question became *"what's actually worth paying for?"* Anything
  Linux/Claude Code/Obsidian already does for free was **subtracted**; what
  remained is an on-demand tool plus one weekly cron — the only job that's
  uniquely Coin's.
- **Cost tracking.** The `usage` MCP reads Claude session files and reports
  tokens/cost/time, so spend is measured, not guessed.

## 8. Cost estimate & local/cloud stack

Only the cloud (Claude API) costs money; everything else runs locally for free.

| Layer | Where | Cost |
|---|---|---|
| OpenClaw gateway, 5 MCP servers, SQLite, Obsidian | Local (laptop) | Free |
| Reasoning (Claude API) | Cloud | Pay-per-token |

**Two-tier model routing** keeps the cloud bill small: Haiku 4.5 handles
everyday calls, and Sonnet 4.6 is reserved for the weekly synthesis. With
`toolsAllow` + `lightContext` trimming each request, the estimated steady-state
cost of the final design — an on-demand tool plus **one weekly cron** — is on
the order of **a few US dollars per month** for personal daily use. The `usage`
MCP measures actual tokens/cost so the estimate stays grounded.

## 9. 7-day usage log summary

`usage-log/USAGE_LOG.md` records **206 MCP-mediated calls over 11 days**
(2026-05-20 → 2026-06-07), exceeding the required 7. Each line is
`HH:MM CHANNEL server task (OUTCOME, latency)`.

| | |
|---|---|
| Days covered | 11 |
| Total calls | 206 (**203 OK, 3 FAILED** → 98.5% success) |
| Channels | CLI 201 · Telegram 5 |
| Busiest servers | `brain` 97 · `schedule` 81 · `spotify/hiphop` 27 |

The log shows real, recurring daily use — and the `brain.recent_logs` /
`read_note` / `schedule.weekly_summary` calls that feed the weekly review.

## 10. Repository layout

```
ai-study-planner/
├── README.md          # this file
├── code/              # MCP servers + scripts (no secrets, no venv, no DBs)
│   └── requirements.txt
├── slides/            # final presentation (PDF)
├── paper/             # term paper
├── usage-log/         # 7-day daily-use evidence (MCP-mediated calls)
└── demo-video/        # ≤ 5-minute screen capture
```

## 11. Privacy & security

Local-first by design. All personal data (journal, listening history, schedule)
stays on the laptop in SQLite + Obsidian markdown and is **excluded** from this
repo via `.gitignore`. Credentials live only in `~/.openclaw/*.json`, never in
source. Telegram access is restricted to a single owner ID, and group messages
require an explicit mention before Coin responds.
