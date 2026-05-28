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

## Security

- Brain binds to `127.0.0.1` only; auth token in `~/.mira/token`
- Mac app reads the token on launch; sends as `Authorization: Bearer`
- All system-control tools require user-confirmation on first use per kind
- Audio capture stays local; only the final transcript is sent to the brain
