# MIRA Architecture

## Components

### 1. Mac App (`mac-app/`)

Native SwiftUI application. Lives in the menu bar; opens a floating chat
panel on a global hotkey. Owns all interactions with the user and the OS:

- **Hotkeys** — `Carbon` / `MASShortcut` for global capture
- **Voice** — `Speech.framework` on-device STT + `AVSpeechSynthesizer` TTS; wake-word via continuous `SFSpeechRecognizer`
- **System control** — Accessibility API, AppleScript bridge, shell exec
- **Vision** — `ScreenCaptureKit` for context-aware help (later)
- **Transport** — talks to the brain over HTTP + WebSocket on `127.0.0.1:7842`

### 2. Brain (`brain/`)

Python FastAPI service. Stateless HTTP surface; state lives in SQLite +
Chroma on disk. Responsibilities:

- **LLM router** — picks Claude (cloud) or Ollama (local) per request
  characteristics (sensitivity, complexity, latency budget)
- **Neuron memory** — episodic store (every turn) + semantic store
  (embeddings) + graph of "neurons" linking related memories
- **Agent orchestrator** — tool-using loop (read screen, run AppleScript,
  search memory, call APIs)
- **Self-learning** — logs every interaction with user feedback; nightly
  job distills patterns into long-term memory

## Data flow (chat turn)

```
User types/speaks
    → Mac app sends {text, context} to POST /chat
    → Brain: retrieve relevant memories (top-k embeddings + graph hops)
    → Brain: route to LLM (Claude if complex, Ollama if simple/private)
    → Brain: stream response tokens back over WebSocket
    → Brain: store turn as a new neuron, link to retrieved ones
    → Mac app renders + (optionally) speaks the reply
```

## Memory model — "neurons"

Each memory is a row:

```
neuron(id, kind, content, embedding, created_at, last_used_at, strength)
edge(src_id, dst_id, kind, weight)
```

`kind` ∈ {turn, fact, preference, skill, observation}. Edges form a
weighted graph; recall traverses both vector-similarity and graph-hops.
Strength decays with time and reinforces on reuse (Hebbian-style).

## LLM routing rules (v0)

| Signal                       | Route to       |
| ---------------------------- | -------------- |
| Contains secret/private flag | Ollama (local) |
| `len(prompt) < 200` and chat | Ollama         |
| Tool use / reasoning needed  | Claude         |
| Image / screen input         | Claude         |
| Cost-sensitive batch         | Ollama         |

Override per-request via `model_hint`.

## Voice (Stage 2)

```
Mic ─► AVAudioEngine ─► SFSpeechAudioBufferRecognitionRequest
                          │
                          ▼
                  partial transcript (live UI)
                          │
                   stop / end-of-speech
                          ▼
                final text ─► POST /chat ─► assistant reply
                                              │
                                              ▼
                                    AVSpeechSynthesizer (TTS)
```

- STT runs **on-device** (`requiresOnDeviceRecognition = true` on macOS 13+);
  no audio leaves the Mac.
- Wake-word listener is a parallel `SFSpeechRecognizer` task that restarts
  on the per-task limit (~1 min) and fires on debounced keyword match.
- Hotkey ⌥⇧Space registered via Carbon `RegisterEventHotKey` (requires
  proper `.app` bundle — see `scripts/build-app.sh`).

## Tools / system control (Stage 3)

Claude's native tool-use is the agent loop. The brain owns declarations
(`brain/mira/agent/tools.py`); the Mac owns execution
(`mac-app/Sources/MIRA/Services/ToolExecutor.swift`). Round-trip:

```
User: "open Safari and go to news.ycombinator.com"
   ↓
Brain → Claude with TOOLS schema + history
   ↓
Claude returns: text + tool_use[{name: run_applescript, input: {script: …}}]
   ↓
Brain responds to Mac: {text, tool_calls:[…], session_id}
   ↓
Mac: ConsentManager.askIfNeeded → ToolExecutor.execute(call)
   ↓
Mac → Brain: agenticChat(session_id, tool_results=[{id, output}])
   ↓
Brain re-calls Claude with appended tool_result blocks
   ↓
Claude returns final text (no more tool_use)
   ↓
Mac displays + speaks the reply
```

Per-kind consent is stored in `UserDefaults` under `mira.consents.v1`.
`shell` is always-ask (never blanket-granted) — too powerful for one-time
consent. The agent loop has a safety cap of 8 tool rounds per user turn.

`remember` is handled brain-side and never round-trips: when Claude calls
it, the brain stores the fact and re-invokes Claude with the result so
the next reply incorporates it.

## Vision (Stage 4)

The `read_screen` tool captures the main display via `ScreenCaptureKit`
(macOS 14+), returns a base64 PNG in the `image_b64` field of the tool
result, and the brain expands that into an Anthropic image content block
inside the `tool_result`. From Claude's perspective the screenshot becomes
just another input it can reason about.

First-time use prompts the standard macOS Screen Recording permission;
revoke any time from System Settings → Privacy & Security → Screen Recording.

## Self-learning (Stage 5)

Three mechanisms work together to turn raw turns into useful long-term memory:

1. **Distillation** (`/learn/distill`) — Claude reads the last N turns and
   proposes durable items (`fact` / `preference` / `skill` / `observation`).
   Each candidate is deduplicated via the vector store before insert.
2. **Decay** (`/learn/decay`) — every neuron's `strength` is multiplied by
   `0.5 ^ (age_seconds / half_life_seconds)`. Unused memory fades.
3. **Feedback** (`/memory/{id}/feedback`) — explicit ±1 reinforcement. The
   Mac client gets the `assistant_neuron_id` in each chat response so it
   can wire ⬆⬇ buttons to specific replies.

Run distill + decay nightly via `launchd`/`cron` for autonomy. Facts,
preferences and skills are protected from pruning even when their
strength dips below the threshold.

## Subscription agent mode (Stage 13)

When agent mode runs without an Anthropic API key, MIRA delegates the
tool-use loop to the user's logged-in `claude` CLI and bridges its own
Mac tools back in over MCP:

- `mira/mcp_server.py` — a stdio MCP server (`mira-tools-server`) advertising
  MIRA's Mac tools (everything in `TOOLS` except brain-only `remember`).
- `mira/agent/cli_bridge.py` — writes `~/.mira/agent-mcp.json` pointing the
  CLI at that server, and computes the `mcp__mira__*` allow-list.
- `orchestrator.agentic_via_cli()` — invokes `claude -p --mcp-config … \
  --allowedTools …`; the CLI runs its loop and calls MIRA's tools.
- `mira/agent/bridge.py` (`ToolBridge`) + `/ws/agent` + `/bridge/execute` —
  the MCP server forwards each tool call to the brain, which routes it over
  a WebSocket to the Mac app, awaits the result (with timeout / disconnect
  handling), and returns it. Consent is still enforced Mac-side.

So the same `ToolExecutor` + `ConsentManager` serve both paths: the
API-key loop (brain returns tool_calls in the /chat response) and the
subscription loop (tools arrive asynchronously over the WebSocket).

## Security

- Brain binds to `127.0.0.1` only; auth token in `~/.mira/token`
- Mac app reads the token on launch; sends as `Authorization: Bearer`
- All system-control tools require user-confirmation on first use per kind
- Audio capture stays local; only the final transcript is sent to the brain
