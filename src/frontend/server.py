import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from ..agent import AgentSession, prewarm as prewarm_llm
from ..stt import prewarm as prewarm_stt
from ..tts import prewarm as prewarm_tts

FRONTEND_DIR = Path(__file__).parent

OLLAMA_HELP = (
    "Cannot connect to Ollama. Start the Ollama app or run `ollama serve`, "
    "then try again."
)


def format_agent_error(exc: Exception) -> str:
    if isinstance(exc, ConnectionError):
        return str(exc)
    name = type(exc).__name__
    msg = str(exc).lower()
    if name == "ConnectError" or "refused" in msg or "10061" in msg:
        return OLLAMA_HELP
    return str(exc)


def prewarm_all() -> str | None:
    try:
        prewarm_llm()
    except Exception as exc:
        return format_agent_error(exc)
    try:
        prewarm_stt()
    except Exception as exc:
        return str(exc)
    try:
        prewarm_tts()
    except Exception as exc:
        return str(exc)
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ready_event = asyncio.Event()
    app.state.prewarm_error: str | None = None

    async def run_prewarm() -> None:
        try:
            app.state.prewarm_error = await asyncio.to_thread(prewarm_all)
        finally:
            app.state.ready_event.set()

    task = asyncio.create_task(run_prewarm())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
turn_lock = asyncio.Lock()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    loop = asyncio.get_running_loop()
    event_queue: asyncio.Queue[dict] = asyncio.Queue()

    def on_event(event: dict) -> None:
        loop.call_soon_threadsafe(event_queue.put_nowait, event)

    session = AgentSession(on_event=on_event)

    async def emit_events() -> None:
        while True:
            event = await event_queue.get()
            await ws.send_json(event)

    emitter = asyncio.create_task(emit_events())

    try:
        await ws.send_json({"type": "status", "state": "loading"})
        await ws.app.state.ready_event.wait()
        if ws.app.state.prewarm_error:
            await ws.send_json(
                {"type": "error", "message": ws.app.state.prewarm_error}
            )
        await ws.send_json({"type": "ready"})
        await ws.send_json({"type": "status", "state": "idle"})
        while True:
            data = await ws.receive_json()
            if turn_lock.locked():
                continue

            action = data.get("action")
            async with turn_lock:
                try:
                    if action == "send":
                        text = data.get("text", "")
                        await asyncio.to_thread(
                            session.send_text, text, speak_reply=True
                        )
                    elif action == "listen":
                        await asyncio.to_thread(session.listen_and_reply)
                except Exception as exc:
                    await ws.send_json(
                        {"type": "error", "message": format_agent_error(exc)}
                    )
                    await ws.send_json({"type": "status", "state": "idle"})
    except WebSocketDisconnect:
        pass
    finally:
        emitter.cancel()


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")


def main() -> None:
    import uvicorn

    from ..config.env import load_env

    load_env()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("src.frontend.server:app", host=host, port=port, reload=True)
