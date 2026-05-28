# MIRA — Memory-Integrated Reasoning Assistant

A native macOS "Jarvis": menu-bar app + Python brain with persistent memory,
voice control, full system access, and hybrid cloud/local LLM routing.

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

## Quick start

```bash
# 1. Brain
cd brain
python -m venv .venv && source .venv/bin/activate
pip install -e .
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

## Metrics

```bash
curl localhost:7842/metrics
# {"uptime_s":…, "neurons_total":…, "neurons_by_kind":{…},
#  "edges_total":…, "avg_strength":…, "sessions_active":…}
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for design details.
