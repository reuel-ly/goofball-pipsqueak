# goofball-pipsqueak

A local voice AI agent with a goofy on-device character. Speak or type; it listens with Whisper, replies through Ollama, and talks back with Kokoro TTS.

## Architecture

Pipeline (shared by CLI, web, and desktop):

```text
Mic / text
    │
    ▼
STT (faster-whisper + WebRTC VAD)     ← optional; skipped for typed input
    │
    ▼
AgentSession                          ← Ollama chat stream + short history
    │
    ├─► TextChunker                   ← phrase boundaries for low-latency speech
    │       │
    │       ▼
    │   TTS (Kokoro) → speakers
    │
    └─► on_event(...)                 ← status / partials / reply text
            │
            ▼
     CLI prints  |  WebSocket → browser / desktop widget
```

| Layer | Role |
| --- | --- |
| **STT** (`src/stt.py`) | Mic capture, VAD endpointing, Whisper transcription, optional partials + level meter |
| **LLM** (`src/agent.py` + Ollama) | Streaming chat; history trimmed to a few turns |
| **Chunker** (`src/chunker.py`) | Turns streamed tokens into speakable phrases so TTS can start before the full reply |
| **TTS** (`src/tts.py`) | Kokoro synthesis + gapless playback; stoppable mid-utterance |
| **Frontends** | Same `AgentSession`; CLI wires print callbacks, web/desktop use FastAPI WebSocket |

**Web / desktop:** FastAPI serves the browser UI and `/ws`. One `AgentSession` lives for the app lifetime (history survives reconnects). The desktop widget is a Tauri app (`desktop/`) with its own frontend; it auto-spawns the backend on launch and connects to the same WebSocket.

**States:** `loading` → `idle` → `listening` / `thinking` / `speaking` (GIFs track these in the UI).

## File structure

```text
goofball-pipsqueak/
├── pyproject.toml          # deps + entry point (pipsqueak-web)
├── .env                    # optional local env (e.g. HF_TOKEN for model downloads)
├── scripts/
│   └── kokoro_tts_sanity_check.py
├── desktop/                # Tauri desktop pet (character + chat bubble)
│   ├── src/                # widget frontend (TS + Vite), character GIFs
│   └── src-tauri/          # Rust shell: window config, backend spawn/kill
├── src/
│   ├── main.py             # CLI voice loop
│   ├── agent.py            # AgentSession: listen / text → LLM → optional TTS
│   ├── stt.py              # Whisper + VAD listen()
│   ├── tts.py              # Kokoro speak / speak_phrases()
│   ├── chunker.py          # Streaming text → phrases
│   ├── config/
│   │   ├── env.py          # load .env from project root
│   │   ├── llm.py          # model, system prompt, Ollama options
│   │   └── stt.py          # sample rate, VAD, Whisper model
│   └── frontend/
│       ├── server.py       # FastAPI + WebSocket + static mount
│       ├── index.html      # browser chat UI
│       ├── app.js
│       └── style.css
└── tests/                  # unit / integration coverage for agent, STT, TTS, etc.
```

## Prerequisites

- **Python 3.11+** and [uv](https://docs.astral.sh/uv/)
- **[Ollama](https://ollama.com/)** running locally, with the model in `src/config/llm.py` pulled (currently `gemma4:e2b-it-qat`):

  ```bash
  ollama pull gemma4:e2b-it-qat
  ```

- Mic and speakers (for voice)
- Optional: `HF_TOKEN` in a project-root `.env` if Hugging Face gated/model downloads need auth for Kokoro

Install deps:

```bash
uv sync
```

## How to run

### CLI

Push-to-talk loop in the terminal (Enter to speak):

```bash
uv run python -m src.main
```

### Desktop widget (Tauri)

Compact always-on-top character window: GIF on top, mic + text input below. Replies stream briefly above the character, then fade after a few seconds.

One-time prerequisites: [Rust toolchain](https://rustup.rs/) (`winget install Rustlang.Rustup` on Windows, plus MSVC C++ Build Tools) and Node.js. Then:

```bash
cd desktop
npm install
npm run tauri dev
```

The app spawns the Python backend automatically (skipped if something is already listening on port 8000) and kills it on exit. Drag the character to move the window; hover the top-right ✕ to close. Type a message or use the mic (`m` when the input is not focused); Escape stops the current turn.

`npm run tauri build` produces an installer, but the machine still needs uv, the Python environment, and Ollama — it is not a standalone distribution.

### Web UI

Start the local server, then open http://127.0.0.1:8000 for the full chat UI:

```bash
uv run pipsqueak-web
```

Or:

```bash
uv run uvicorn src.frontend.server:app --reload
```

Optional env overrides for the web server: `HOST` (default `127.0.0.1`), `PORT` (default `8000`).

### Tests

```bash
uv run pytest
```

## Configuration

| File | What you typically change |
| --- | --- |
| `src/config/llm.py` | Ollama model, system prompt, history length, thread/GPU options |
| `src/config/stt.py` | Whisper model size, VAD silence / utterance limits |
| `src/tts.py` | Kokoro voice (`VOICE`) |

First launch pre-warms LLM, Whisper, and TTS; that can take a bit on cold start.
