# MIRA — Memory-Integrated Reasoning Assistant

A native macOS "Jarvis": menu-bar app + Python brain with persistent memory,
voice control, full system access, and hybrid cloud/local LLM routing.

## Install

**One line** (sets up the brain, builds & installs the app, registers the
login agent, asks for your API key):

```bash
curl -fsSL https://raw.githubusercontent.com/railers1991-jpg/mira/main/install.sh | bash
```

**Or download the app** — grab the latest `MIRA-*.dmg` from
[Releases](https://github.com/railers1991-jpg/mira/releases), open it, and drag
MIRA to Applications. On first launch the app checks for its local brain and,
if it's missing, shows you the one-liner above.

> The app is ad-hoc signed (no paid Apple Developer ID yet). First launch:
> right-click MIRA → **Open** → **Open**, or run
> `xattr -dr com.apple.quarantine /Applications/MIRA.app`.

Requirements: macOS 14+, Python 3.11+, Xcode Command Line Tools. Apple Silicon
recommended for on-device speech. Cloud reasoning needs an
[Anthropic API key](https://console.anthropic.com/); without one MIRA runs
local-only via [Ollama](https://ollama.com).

**Update**: re-run the one-liner. **Uninstall**: `~/.mira/src/scripts/uninstall.sh`
(add `--purge` to also delete memory/sessions/skills).

## Architecture

```
┌──────────────────────────────────┐
│  Mac App (Swift / SwiftUI)       │
│  • Menu-bar + floating panel     │
│  • Global hotkeys                │
│  • Voice I/O (AVFoundation)      │
│  • Accessibility / AppleScript   │
└──────────────┬───────────────────┘
               │ HTTP / WebSocket (localhost)
┌──────────────▼───────────────────┐
│  Brain (Python / FastAPI)        │
│  • LLM router (Claude + Ollama)  │
│  • Neuron memory (SQLite+Chroma) │
│  • Agent orchestrator + tools    │
│  • Self-learning loop            │
└──────────────────────────────────┘
```

## Roadmap

- [x] **Stage 1** — Skeleton: chat, memory, hybrid LLM routing
- [x] **Stage 2** — Voice: on-device STT (Speech framework), TTS, wake-word, ⌥⇧Space hotkey
- [x] **Stage 3** — System control: tool-use loop (AppleScript, shell, open_url, notify, get_active_app, remember)
- [x] **Stage 4** — Vision: `read_screen` tool via ScreenCaptureKit → image block to Claude
- [x] **Stage 5** — Self-learning: distillation, neuron decay, feedback signals
- [x] **Stage 6** — Polish: conversation memory, autonomous scheduler, JSON SSE, multi-display vision, metrics, launchd
- [x] **Stage 7** — More tools: clipboard, file read, type into focused field
- [x] **Stage 8** — Persistent sessions: SQLite-backed, sidebar UI, auto-titles via Claude
- [x] **Stage 9** — Dictate Anywhere: ⌃⌥V records from anywhere → types into the focused field
- [x] **Stage 10** — MCP plugin host: connect any MCP server (Gmail, Calendar, Notion, web search…), tools auto-exposed to Claude
- [x] **Stage 11** — Self-forged skills: MIRA distils successful chats into named, reusable procedures that auto-expose as Claude tools and accumulate lessons
- [x] **Stage 12** — Subscription providers: run reasoning through your Claude Pro/Max or ChatGPT/Codex plan via their CLIs — no API key required
- [x] **Stage 13** — Subscription agent mode: MIRA's Mac tools bridged into the `claude` CLI over MCP, so full system-control works on a subscription too

## Run from source (development)

```bash
# 1. Brain
cd brain
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
export ANTHROPIC_API_KEY=sk-ant-...
mira-brain  # FastAPI on :7842

# 2. Mac app (on macOS) — build a proper .app so mic & hotkey work
./scripts/build-app.sh
open mac-app/MIRA.app
```

On first launch macOS will ask for **Microphone** and **Speech Recognition** access.
For ⌥⇧Space global hotkey: System Settings → Privacy & Security → **Accessibility** → enable MIRA.

## Voice

- **Push-to-talk** — click the mic in the chat panel, speak, click again (or wait
  for end-of-speech). Transcript is shown live.
- **Wake word** — toggle in Settings → Voice. Listens for "Мира" / "MIRA" and
  opens the chat panel.
- **TTS** — assistant replies are spoken automatically. Toggle 🔊 in the chat header.
- **Dictate Anywhere** — ⌃⌥V from any app: HUD appears, you speak, ⌃⌥V again,
  and the transcript is typed into whichever field has focus. No chat panel
  needed, works in Notes/Slack/Xcode/Mail/anywhere.
- All speech recognition runs **on-device** (Apple Silicon required for best results).

## Tools (Stage 3)

Toggle ⚙︎ in the chat header to allow MIRA to use tools. Available actions:

| Tool              | What it does                                          |
| ----------------- | ----------------------------------------------------- |
| `run_applescript` | Run an AppleScript (app control, file ops, GUI)       |
| `shell`           | Run a shell command (always asks per invocation)      |
| `open_url`        | Open a URL in the default browser                     |
| `notify`          | Show a macOS notification                             |
| `get_active_app`  | Read the frontmost app's bundle id, name, pid         |
| `remember`        | Persist a fact/preference into long-term memory       |
| `read_screen`     | Capture a display (multi-display via `display_index`) for Claude |
| `read_clipboard`  | Read the current clipboard text                       |
| `write_clipboard` | Replace the clipboard contents                         |
| `read_file`       | Read a UTF-8 file (capped, ~-expansion supported)     |
| `type_text`       | Type into the focused field via CGEvent (Accessibility) |

Each tool kind asks for consent on first use; ⌃ Settings → Tools manages grants.
Tool use always routes to Claude (Ollama function-calling is unreliable for now).

## Self-learning (Stage 5)

Three endpoints turn raw conversation history into longer-lived memory:

```bash
# Extract durable facts/preferences from the last N turns
curl -X POST localhost:7842/learn/distill?limit=50

# Decay strengths (Hebbian forgetting), then prune the weakest non-facts
curl -X POST localhost:7842/learn/decay \
  -H 'Content-Type: application/json' \
  -d '{"half_life_days": 30, "prune_below": 0.05}'

# Reinforce or weaken a single neuron (e.g. on user thumbs-up/down)
curl -X POST localhost:7842/memory/<neuron_id>/feedback \
  -H 'Content-Type: application/json' \
  -d '{"signal": "positive"}'
```

Schedule `decay` and `distill` nightly via `launchd` or `cron`; MIRA will
gradually forget noise while crystallising what matters about you.

For autonomy out of the box, the brain runs the same loop itself every
`MIRA_DISTILL_INTERVAL_S` seconds (default 24h). Set the variable to `0`
to disable.

## Run on login

```bash
# Stores brain logs in ~/.mira/logs and reads env from ~/.mira/env
./scripts/install-launchd.sh
echo 'ANTHROPIC_API_KEY=sk-ant-...' > ~/.mira/env
launchctl kickstart -k "gui/$UID/com.mira.brain"
```

## MCP plugins

MIRA hosts any [Model Context Protocol](https://modelcontextprotocol.io)
server you configure — their tools appear under `mcp__<server>__<tool>`
and are routed automatically through the same Claude tool-loop as
MIRA's native tools.

```bash
cp docs/mcp.example.json ~/.mira/mcp.json
# edit paths / env vars to point at your installed MCP servers
launchctl kickstart -k "gui/$UID/com.mira.brain"   # restart to reconnect
curl localhost:7842/tools                          # introspect what's available
```

The brain hands the merged tool list to Claude; when Claude calls an
MCP tool, the brain executes it via the connected server and feeds the
result back without round-tripping to the Mac. Local-only access:
servers run as subprocesses, MCP traffic stays on stdio.

## Reasoning providers — use your subscription, not just an API key

MIRA can drive its reasoning through whatever you already pay for. The
installer detects what's present and lets you choose; you can also set
`MIRA_PROVIDER` in `~/.mira/env` and restart the brain.

| Provider | `MIRA_PROVIDER` | How it authenticates | Tool-use (agent mode) |
| --- | --- | --- | --- |
| Anthropic API | `api` | `ANTHROPIC_API_KEY` | ✅ |
| Claude Pro/Max | `claude_code` | `claude login` (Claude Code CLI) | — (chat/skills only) |
| ChatGPT/Codex | `codex` | `codex login` (Codex CLI) | — (chat/skills only) |
| Ollama (local) | `local` | offline | — |
| Auto | `auto` | api → claude_code → codex → local | ✅ if a key is present |

The subscription providers shell out to the **official** `claude` / `codex`
CLIs in non-interactive mode — MIRA never reads or stores your credentials;
each CLI manages its own login session. Anything matching a privacy pattern
(passwords, secrets, tokens) is always forced to the local model regardless
of the selected provider.

### Agent mode on a subscription

With the `claude` CLI logged into Pro/Max, MIRA gets **full agent mode**
(system control, vision, clipboard…) on your subscription — no API key.

How it works: the brain hosts a stdio MCP tools server (`mira-tools-server`)
exposing its Mac tools. When agent mode runs without an API key, MIRA invokes
`claude -p --mcp-config …` so the CLI's own loop can call those tools. Each
call flows MCP server → brain bridge → a WebSocket to the Mac app, which runs
it through `ToolExecutor` with the usual consent, then returns the result
(including screenshots). The CLI sees MIRA's tools as `mcp__mira__*`.

```
claude CLI (Pro/Max)
   │ spawns mira-tools-server (stdio MCP)
   ▼
mira-tools-server ──HTTP /bridge/execute──► Brain ToolBridge
                                                 │ WebSocket /ws/agent
                                                 ▼
                                       Mac app · ToolExecutor + consent
```

```bash
curl localhost:7842/providers   # see what's available and what's active
```

## Skills — MIRA learns on the fly

After a useful agent-mode conversation, tap the ✨ in the chat header
(or `POST /skills/forge`) and Claude distils that interaction into a
named, parameterised skill stored in SQLite. From then on the skill
appears alongside built-in tools (`skill__<name>`) and Claude can
pick it whenever its `when_to_use` matches the user's request.

Each skill has:
- **steps** — a deterministic playbook: `prompt` steps call Claude with
  templated text, `tool` steps invoke MCP servers or other skills,
  results are saved in a shared `{{var}}` context
- **lessons** — short strings MIRA writes after runs to refine itself
  (capped at 20, deduped, last 3 surfaced in the tool description)
- **success_count / failure_count** — track reliability per skill

```bash
# Browse the catalogue
curl localhost:7842/skills

# Run a skill directly (the agent loop also calls them automatically)
curl -X POST localhost:7842/skill/summarize_unread/run \
  -H 'Content-Type: application/json' \
  -d '{"senders": ["alice@example.com"]}'

# Forge from a recent session
curl -X POST localhost:7842/skills/forge \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "<sid>"}'

# Append a lesson based on an outcome
curl -X POST localhost:7842/skill/summarize_unread/lesson \
  -H 'Content-Type: application/json' \
  -d '{"outcome": "user wanted bullets, not prose"}'
```

This is the unique angle: no other Mac assistant compiles your
conversations into a growing personal catalogue of executable skills
that get better the more you use them.

## Metrics

```bash
curl localhost:7842/metrics
# {"uptime_s":…, "neurons_total":…, "neurons_by_kind":{…},
#  "edges_total":…, "avg_strength":…, "sessions_active":…}
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for design details.
