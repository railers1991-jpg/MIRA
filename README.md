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
- [ ] **Stage 2** — Voice: Whisper STT, wake-word, TTS
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

# 2. Mac app (on macOS)
cd mac-app
swift run    # or open Package.swift in Xcode
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for design details.
