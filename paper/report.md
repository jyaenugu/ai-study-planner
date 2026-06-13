# Coin: A Private, Note-Grounded AI Study Planner for Graduate Students

**Seohee Han** · Generative AI and Blockchain, GIST · June 2026
*Project type (i): Personal AI Butler*

---

## Abstract

Graduate research removes the explicit yardstick of undergraduate exams:
there is no weekly score, advisor feedback is coarse, and general-purpose
chatbots are stateless strangers that return plausible-sounding generalities
because they have no memory of the student. This paper presents **Coin**, a
private Personal AI Butler that runs entirely on a personal laptop. Coin wires
**Claude** into a graduate student's real tools — Obsidian notes, a schedule
store, a music log, and a blog — through five self-authored **MCP (Model
Context Protocol)** servers, and is reached conversationally through Telegram.
Its defining capability is a **weekly research review** produced by
**Retrieval-Augmented Generation (RAG)**: it retrieves the week's journal, the
student's research-goal file, and an activity summary, then generates feedback
*grounded in those records* rather than inventing them. We analyze the system
through the course's agent-intelligence frame **I = M × HBM × R** and show
non-trivial mass in all three factors, document the cost and rate-limit
engineering that makes daily use affordable, and present an 11-day usage log as
practicality evidence.

## I. Introduction

The transition from undergraduate to graduate study removes a feedback signal
that students rarely notice until it is gone. Exams provided a recurring,
quantitative answer to *"am I doing okay?"*. Research provides none. The weekly
lab meeting is the only structured checkpoint, and it is necessarily coarse —
an advisor cannot give fine-grained, day-level feedback, and a student cannot
report everything.

Three existing tools fail to fill this gap:

1. **Paper planners** are tedious to maintain, are designed for exam-driven
   study, and give no feedback.
2. **General chatbots** (ChatGPT, Gemini) have no persistent memory of the
   student's goals; each session starts from zero, so advice is generic and
   nothing accumulates.
3. **Note apps** (Obsidian, Notion) store records faithfully but do not
   *reason* over them.

We argue that the missing artifact is a **personalized planner that (a)
remembers the student and (b) gives weekly feedback grounded in the student's
own records.** This paper describes such a system, Coin, built as a private AI
butler on the OpenClaw + Claude + MCP stack.

## II. System Architecture

Coin runs on an LG gram 16 (Intel i7-1195G7, 16 GB RAM) under Ubuntu 24.04 LTS.
The OpenClaw gateway runs continuously as a `systemd` service, so the assistant
is always reachable. The user interface is a Telegram bot; the reasoning
engine is the Claude API; the connection to the user's data is MCP.

```
        Telegram ──────▶┌──────────────┐◀────── Obsidian Vault (.md notes)
        (chat UI)        │  OpenClaw     │◀────── Notion (read-anywhere mirror)
   Claude API ─────────▶│  gateway      │──────▶ Jekyll blog (GitHub Pages)
   (Sonnet/Haiku)        │  = "Coin"     │◀────── Spotify (listening log)
                         └──────────────┘
                                │
                             fetch (web)
```

**MCP servers.** Five local servers expose the user's tools to Claude. None
stores credentials in source; each reads secrets from `~/.openclaw/*.json` at
runtime.

| Server | Tools | Function |
|---|---:|---|
| `brain` | 13 | Read / search / write the Obsidian Vault |
| `schedule` | 17 | Calendar, todos, commitments, `weekly_summary` |
| `spotify` | 15 | Listening log, "obsessed-on", playback, heatmap |
| `blog` | 6 | Publish posts/news to a Jekyll GitHub Pages blog |
| `usage` | 5 | Token/cost/time tracking from Claude session files |
| `fetch` | — | Read-only web access (`mcp-server-fetch`) |

## III. The Core Mechanism: Note-Grounded Weekly Review (RAG)

A weekly review is the one task a generic chatbot cannot perform, because the
required context — *this student's* week — does not exist in its weights. Coin
treats the review as a Retrieval-Augmented Generation problem:

```
My notes ──▶ retrieve ──▶ Claude Sonnet ──▶ weekly review
(Obsidian)   (brain MCP)   (grounded)        (saved to Vault + Notion)
```

**Retrieval.** Before any text is generated, Coin pulls three sources:

1. `brain.recent_logs(7)` — the week's seven journal entries
2. `brain.read_note("RESEARCH_GOALS")` — the student's goal file
3. `schedule.weekly_summary` — the week's activity mix

**Generation.** Claude composes the review *grounded in* that retrieved
context. In the demo, the review correctly states that the student "finished
the DAE paper," prepared "the lab-meeting PPT," and "slept at 5 AM" — each fact
retrieved from a journal entry, not hallucinated. A plain chatbot, lacking
these records, instead produces plausible-sounding generalities. This contrast
is the project's central empirical claim.

## IV. Analysis Frame: I = M × HBM × R

Week 10 framed LLM-substrate intelligence as *I = Compute × Memory ×
Retrieval*. We re-map this at the **agent layer**:

$$ I_{\text{agent}} = M \times \text{HBM} \times R $$

- **M = curated `.md` state** — the student's accumulating Obsidian notes.
- **HBM = chosen model / context** — which model is invoked and what context
  is loaded.
- **R = MCP / RAG / tool** — the retrieval and action layer.

The product is **multiplicative**: any factor near zero collapses agent
intelligence. The course requires demonstrating non-trivial mass in all three.

**M (curated state) — non-trivial.** Coin's memory is not a chat buffer but a
structured, growing Vault: daily journal entries, a `RESEARCH_GOALS.md` goal
file, Brain notes (books, papers, insights), and saved weekly reviews. Over the
evaluation window the journal alone accumulated 11 days of structured entries
with tags (`#research`, `#paper`, …). This is durable, query-able state, not
ephemeral context. *Failure mode avoided:* with low M the butler would be
stateless and forget the user.

**HBM (model / context) — non-trivial.** Coin deliberately routes work across a
**two-tier model stack**: Haiku 4.5 for everyday calls and Sonnet 4.6 reserved
for the weekly synthesis where reasoning quality matters. Context is actively
shaped — `lightContext` trims persona and background to the minimum, and
`toolsAllow` exposes only the ~6 tools a weekly review needs instead of all
~50. This is an explicit model/context-selection policy, not a default.
*Failure mode avoided:* with low HBM the butler could not load consolidated
memory within the model's usable context.

**R (retrieval / tools) — non-trivial.** Five MCP servers expose ~50 tools, and
the weekly review exercises a genuine RAG pipeline (Section III) that retrieves
from the Vault and schedule store before generating. Retrieval is observable in
the usage log as concrete tool calls with outcomes and latencies. *Failure mode
avoided:* with low R the butler would work from stale data and hallucinate the
present.

Because all three factors carry real mass, the product — useful agent
intelligence — does not collapse.

## V. Cost and Rate-Limit Engineering

**The rate-limit wall.** The Anthropic API Tier-1 limit is 30,000 input tokens
per minute. A naive agent re-sends, on every step, (1) the entire conversation
so far and (2) the tool manuals for all ~50 tools — so even "read one note"
can exceed 30k and the API rejects the request. It is like re-reading 50
manuals from scratch before every errand.

**Fix: shrink what gets sent.** Three measures, in order of impact:

1. **`toolsAllow`** — expose only the ~6 tools a weekly review actually needs;
   drop the other ~44 manuals. (Largest saving.)
2. **`lightContext`** — trim persona and background context to the minimum.
3. **Model choice** — Sonnet only for the weekly synthesis; the cheap model
   otherwise.

Result: requests fit under 30k, the rate-limit errors disappear, and per-call
cost drops. Building the agent *light* yields stability and savings at once.

**Cost economy.** Because the system bills per token rather than by
subscription, the design question is not "what *can* it do?" but "what is
*worth paying for*?" Capabilities that free local software already provides were
deliberately **subtracted**:

| Capability | Decision | Reason |
|---|---|---|
| Sending email | removed | I can send it myself |
| Spotify / Notion sync | removed | Linux cron already does it, free |
| Daily song alerts | removed | just open Obsidian / Notion |
| Blog edits | removed | Claude Code does it better |
| **Weekly research feedback** | **kept** | **only Coin can do this** |

What remains is an on-demand tool plus a single weekly cron job — the one task
that is uniquely Coin's. The `usage` MCP measures tokens, cost, and active time
from Claude session files, so spend is monitored rather than guessed.

## VI. Privacy and Security

**Local-first data flow.** All personal data is created and stored on the
laptop and never leaves it except as the minimal context a single Claude
request requires:

```
[Obsidian .md] ─┐
[schedule.db]  ─┼─▶ MCP server (local) ─▶ minimal context ─▶ Claude API
[spotify.db]   ─┘        (on laptop)          (per request)     (cloud)
       ▲                                                          │
       └──────────────── grounded answer written back ───────────┘
```

**Threat model.**

| Asset | Threat | Mitigation |
|---|---|---|
| API / bot keys | Leak via source repo | Secrets only in `~/.openclaw/*.json`; `.gitignore` excludes them; repo scanned for hard-coded keys (none found) |
| Personal records (journal, spend, listening) | Exposure in public repo | All `*.db` and Vault content excluded from the repo |
| Unauthorized bot use | Stranger messages the bot | Telegram restricted to a single owner ID; group messages require explicit mention |
| Cloud over-exposure | Whole Vault sent to API | `lightContext` + `toolsAllow` send only the slice a request needs |

**Incidents.** Zero security incidents during the project period; no credential
was committed and no personal data left the device beyond per-request context.

## VII. Differentiation vs. Big-Tech Assistants

OpenClaw advantages demonstrated (≥3 required):

1. **Local & private** — runs on my laptop; records never centralize in a
   vendor cloud.
2. **Note-grounded (RAG)** — feedback cites my real records instead of
   inventing generalities.
3. **Accumulating memory** — the Vault grows, so each week's review is better
   informed than the last.
4. **Self-extensible via MCP** — five servers I wrote connect Claude to
   Obsidian, Notion, Spotify, my blog, and the web.
5. **Cost-bounded** — a two-tier model stack and trimmed context keep daily use
   under the rate limit and affordable.

## VIII. Evaluation

**Practicality (primary metric).** An 11-day usage log (`usage-log/`) records
MCP-mediated calls in the form `HH:MM CHANNEL server task (OUTCOME, latency)`
across two channels (CLI and Telegram). It evidences daily, real use rather
than a one-off demo, and shows the retrieval calls underlying the weekly
review. (The course requires a 7-day log; 11 days are provided.)

**Qualitative.** In the recorded demo the weekly review reproduces
week-specific facts (DAE paper completion, lab-meeting PPT, a 5 AM sleep night,
a 23,900-KRW stopwatch purchase flagged as the week's largest single expense),
none of which a memoryless chatbot could supply.

## IX. Future Work

1. **Counsel first, then feedback.** Before writing a review, ask ~5 short
   questions over Telegram ("Why didn't the paper get read?", "What felt most
   stuck this week?") and fold the answers into the feedback, turning a one-way
   review into coaching.
2. **Smarter as records stack.** As weeks accumulate into months and quarters,
   surface longitudinal patterns ("this month vs. last quarter", "what keeps
   getting pushed back?") and let the review refine `RESEARCH_GOALS.md` over
   time.

## X. Conclusion

Coin shows that a useful private AI butler for a graduate student is not a
matter of raw model capability but of getting three multiplicative factors all
non-trivial at once: a curated, accumulating note state (M); deliberate model
and context selection (HBM); and a real MCP/RAG retrieval layer (R). Grounding
generation in the student's own records turns a generic chatbot into a planner
that remembers, and disciplined cost and context engineering makes it cheap
enough to use every day.

## References

[1] OpenClaw documentation. https://openclaw.ai
[2] Anthropic, "Claude API and Model Context Protocol (MCP)."
[3] H.-N. Lee, "Building a Useful Private AI Butler," GIST INFONET Lab, course
    notes (Week 10: *Intelligence = Compute × Memory × Retrieval*), 2026.
