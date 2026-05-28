"""Voice I/O.

Stage 2 ships on-device on the Mac client (Apple Speech framework + AVSpeechSynthesizer);
the brain receives final transcripts as plain text via POST /chat. No audio
crosses the wire today.

Stage 2.5 (future): optional server-side `faster-whisper` fallback for
clients without on-device STT (Linux/Windows companion apps). Will live
here as `transcribe.py` with a streaming WebSocket endpoint.
"""
