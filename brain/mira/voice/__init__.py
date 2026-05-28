"""Voice I/O — Stage 2.

Planned:
- STT via faster-whisper (on-device, GPU if available)
- TTS via Piper (local) or ElevenLabs (cloud)
- Wake-word via Porcupine

Mac app captures audio; brain receives raw PCM frames over WebSocket.
"""
