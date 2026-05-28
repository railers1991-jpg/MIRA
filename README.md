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
- [ ] **Stage 3** — System control: Accessibility API, AppleScript tools
- [ ] **Stage 4** — Vision: screen capture + multimodal understanding
- [ ] **Stage 5** — Self-learning: feedback loops, fine-tuning on user logs

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

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for design details.
