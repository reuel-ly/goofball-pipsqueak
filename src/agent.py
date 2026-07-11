import queue
import threading
from collections.abc import Callable, Iterator

import ollama

from .chunker import TextChunker
from .config.llm import MAX_HISTORY_TURNS, MODEL, SYSTEM, THINK, ollama_options
from .stt import listen
from .tts import speak_phrases

_TIMEOUT_POLL_S = 0.05


def prewarm() -> None:
    print("Pre-warming LLM...")
    ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": "hi"}],
        options=ollama_options(num_predict=1),
    )
    print("LLM ready.")


def _timeout_flusher(
    chunker: TextChunker,
    phrase_queue: queue.Queue[str | None],
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set():
        for phrase in chunker.check_timeout():
            phrase_queue.put(phrase)
        stop_event.wait(_TIMEOUT_POLL_S)


class AgentSession:
    def __init__(self, on_event: Callable[[dict], None] | None = None):
        self.history = [{"role": "system", "content": SYSTEM}]
        self.on_event = on_event or (lambda _: None)
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        """Interrupt the current turn: stop generation, playback, or listening."""
        self._stop_event.set()

    def _emit(self, event: dict) -> None:
        self.on_event(event)

    def _trim_history(self) -> None:
        max_messages = MAX_HISTORY_TURNS * 2
        if len(self.history) <= 1 + max_messages:
            return
        self.history = [self.history[0], *self.history[-max_messages:]]

    def _stream_chat(self) -> Iterator[str]:
        self._trim_history()
        for chunk in ollama.chat(
            model=MODEL,
            messages=self.history,
            stream=True,
            think=THINK,
            options=ollama_options(),
        ):
            token = chunk["message"]["content"]
            if token:
                yield token

    def _generate_reply(self, *, speak_reply: bool = False) -> str:
        chunker = TextChunker()
        phrase_queue: queue.Queue[str | None] | None = (
            queue.Queue() if speak_reply else None
        )
        reply_parts: list[str] = []
        flusher_stop = threading.Event()
        tts_thread: threading.Thread | None = None
        timeout_thread: threading.Thread | None = None

        if speak_reply and phrase_queue is not None:

            def on_first_phrase() -> None:
                self._emit({"type": "status", "state": "speaking"})

            tts_thread = threading.Thread(
                target=speak_phrases,
                args=(phrase_queue,),
                kwargs={
                    "on_first_phrase": on_first_phrase,
                    "stop_event": self._stop_event,
                },
                daemon=True,
            )
            tts_thread.start()
            timeout_thread = threading.Thread(
                target=_timeout_flusher,
                args=(chunker, phrase_queue, flusher_stop),
                daemon=True,
            )
            timeout_thread.start()

        stopped = False
        for token in self._stream_chat():
            if self._stop_event.is_set():
                stopped = True
                break
            reply_parts.append(token)
            self._emit({"type": "assistant_partial", "delta": token})

            if speak_reply and phrase_queue is not None:
                for phrase in chunker.add(token):
                    phrase_queue.put(phrase)

        reply = "".join(reply_parts)

        if speak_reply and phrase_queue is not None:
            flusher_stop.set()
            if not stopped:
                for phrase in chunker.flush():
                    phrase_queue.put(phrase)
            phrase_queue.put(None)
            if tts_thread:
                tts_thread.join()
            if timeout_thread:
                timeout_thread.join()

        return reply

    def send_text(self, text: str, *, speak_reply: bool = False) -> str | None:
        self._stop_event.clear()
        text = text.strip()
        if not text:
            self._emit({"type": "status", "state": "idle"})
            return None

        self._emit({"type": "user", "text": text})
        self.history.append({"role": "user", "content": text})

        self._emit({"type": "status", "state": "thinking"})
        reply = self._generate_reply(speak_reply=speak_reply)

        self.history.append({"role": "assistant", "content": reply})
        self._emit({"type": "assistant", "text": reply})

        self._emit({"type": "status", "state": "idle"})
        return reply

    def listen_and_reply(self) -> str | None:
        self._stop_event.clear()
        self._emit({"type": "status", "state": "listening"})

        def on_partial(text: str) -> None:
            self._emit({"type": "partial", "text": text})

        def on_level(value: float) -> None:
            self._emit({"type": "level", "value": value})

        text = listen(
            on_partial=on_partial,
            on_level=on_level,
            stop_event=self._stop_event,
        )
        if not text or self._stop_event.is_set():
            self._emit({"type": "status", "state": "idle"})
            return None

        return self.send_text(text, speak_reply=True)
