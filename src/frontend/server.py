import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from ..agent import AgentSession

FRONTEND_DIR = Path(__file__).parent

app = FastAPI()
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
                        await asyncio.to_thread(session.send_text, text, False)
                    elif action == "listen":
                        await asyncio.to_thread(session.listen_and_reply)
                except Exception as exc:
                    await ws.send_json({"type": "error", "message": str(exc)})
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
