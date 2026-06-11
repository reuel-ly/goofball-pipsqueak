from collections.abc import Callable

import ollama

from .config.llm import MODEL, SYSTEM
from .stt import listen
from .tts import speak


class AgentSession:
    def __init__(self, on_event: Callable[[dict], None] | None = None):
        self.history = [{"role": "system", "content": SYSTEM}]
        self.on_event = on_event or (lambda _: None)

    def _emit(self, event: dict) -> None:
        self.on_event(event)

    def send_text(self, text: str, *, speak_reply: bool = False) -> str | None:
        text = text.strip()
        if not text:
            self._emit({"type": "status", "state": "idle"})
            return None

        self._emit({"type": "user", "text": text})
        self.history.append({"role": "user", "content": text})

        self._emit({"type": "status", "state": "thinking"})
        resp = ollama.chat(model=MODEL, messages=self.history)
        reply = resp["message"]["content"]

        self.history.append({"role": "assistant", "content": reply})
        self._emit({"type": "assistant", "text": reply})

        if speak_reply:
            self._emit({"type": "status", "state": "speaking"})
            speak(reply)

        self._emit({"type": "status", "state": "idle"})
        return reply

    def listen_and_reply(self) -> str | None:
        self._emit({"type": "status", "state": "listening"})

        def on_partial(text: str) -> None:
            self._emit({"type": "partial", "text": text})

        text = listen(on_partial=on_partial)
        if not text:
            self._emit({"type": "status", "state": "idle"})
            return None

        return self.send_text(text, speak_reply=True)
