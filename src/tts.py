import queue
import threading
from collections.abc import Callable

import numpy as np
import sounddevice as sd
from kokoro import KPipeline

SAMPLERATE = 24000
VOICE = "af_heart"

_tts = None


def _get_pipeline():
    global _tts
    if _tts is None:
        _tts = KPipeline(lang_code="a")
    return _tts


def _iter_audio_chunks(text: str):
    for _, _, audio in _get_pipeline()(text, voice=VOICE):
        if audio.size:
            yield audio


def synthesize(text: str) -> np.ndarray:
    chunks = list(_iter_audio_chunks(text))
    if not chunks:
        return np.array([], dtype=np.float32)
    return np.concatenate(chunks)


def prewarm() -> None:
    print("Pre-warming TTS...")
    _get_pipeline()
    synthesize("Hello.")
    print("TTS ready.")


class AudioPlayer:
    """Play audio segments sequentially from a queue."""

    def __init__(self, samplerate: int = SAMPLERATE):
        self._samplerate = samplerate
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enqueue(self, audio: np.ndarray) -> None:
        if audio.size:
            self._queue.put(audio)

    def finish(self) -> None:
        self._queue.put(None)

    def wait(self) -> None:
        if self._thread:
            self._thread.join()

    def _run(self) -> None:
        while True:
            audio = self._queue.get()
            if audio is None:
                break
            sd.play(audio, samplerate=self._samplerate)
            sd.wait()


def speak(text: str) -> None:
    audio = synthesize(text)
    if audio.size:
        sd.play(audio, samplerate=SAMPLERATE)
        sd.wait()


def speak_phrases(
    phrase_queue: queue.Queue[str | None],
    *,
    on_first_phrase: Callable[[], None] | None = None,
) -> None:
    """Synthesize and play phrases from a queue until a None sentinel is received."""
    player = AudioPlayer()
    player.start()
    first = True

    while True:
        phrase = phrase_queue.get()
        if phrase is None:
            break
        for chunk in _iter_audio_chunks(phrase):
            if first and on_first_phrase:
                on_first_phrase()
                first = False
            player.enqueue(chunk)

    player.finish()
    player.wait()
