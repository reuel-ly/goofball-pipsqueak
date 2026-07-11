import os

# Must be set before torch/OpenMP is first imported, or it has no effect.
os.environ.setdefault("OMP_NUM_THREADS", "4")

import queue
import threading
from collections.abc import Callable

import numpy as np
import sounddevice as sd
import torch
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
    torch.set_num_threads(4)
    print("Pre-warming TTS...")
    _get_pipeline()
    synthesize("Hello.")
    print("TTS ready.")


class AudioPlayer:
    """Play queued audio gaplessly through one persistent output stream.

    The stream outputs silence while waiting for the next chunk, so
    consecutive phrases play back-to-back without the click/pause caused
    by opening and closing a stream per chunk.
    """

    def __init__(self, samplerate: int = SAMPLERATE):
        self._samplerate = samplerate
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._pending = np.empty(0, dtype=np.float32)
        self._done_seen = False
        self._finished = threading.Event()
        self._stream: sd.OutputStream | None = None

    def start(self) -> None:
        self._stream = sd.OutputStream(
            samplerate=self._samplerate,
            channels=1,
            dtype="float32",
            callback=self._callback,
            finished_callback=self._finished.set,
        )
        self._stream.start()

    def enqueue(self, audio: np.ndarray) -> None:
        if audio.size:
            self._queue.put(np.asarray(audio, dtype=np.float32))

    def finish(self) -> None:
        """Signal that no more audio will be enqueued."""
        self._queue.put(None)

    def stop(self) -> None:
        """Abort playback immediately, discarding any queued audio."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._done_seen = True
        self._pending = np.empty(0, dtype=np.float32)
        if self._stream is not None:
            self._stream.abort()
        self._finished.set()
        self._close()

    def wait(self, timeout: float | None = None) -> bool:
        """Block until playback finishes. Returns True once done."""
        if self._stream is None:
            return True
        if not self._finished.wait(timeout):
            return False
        self._close()
        return True

    def _close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def _callback(self, outdata, frames, time_info, status) -> None:
        out = outdata[:, 0]
        filled = 0
        while filled < frames:
            if self._pending.size == 0:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if item is None:
                    self._done_seen = True
                    break
                self._pending = item
            n = min(frames - filled, self._pending.size)
            out[filled : filled + n] = self._pending[:n]
            self._pending = self._pending[n:]
            filled += n
        if filled < frames:
            out[filled:] = 0.0
        if self._done_seen and self._pending.size == 0:
            raise sd.CallbackStop


def speak(text: str) -> None:
    audio = synthesize(text)
    if audio.size:
        sd.play(audio, samplerate=SAMPLERATE)
        sd.wait()


def speak_phrases(
    phrase_queue: queue.Queue[str | None],
    *,
    on_first_phrase: Callable[[], None] | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """Synthesize and play phrases from a queue until a None sentinel is received.

    If stop_event is set, playback aborts immediately and remaining phrases
    are drained without being synthesized.
    """
    player = AudioPlayer()
    player.start()
    first = True

    def stopped() -> bool:
        return stop_event is not None and stop_event.is_set()

    while True:
        phrase = phrase_queue.get()
        if phrase is None:
            break
        if stopped():
            continue
        for chunk in _iter_audio_chunks(phrase):
            if stopped():
                break
            if first and on_first_phrase:
                on_first_phrase()
                first = False
            player.enqueue(chunk)

    if stopped():
        player.stop()
        return

    player.finish()
    while not player.wait(timeout=0.1):
        if stopped():
            player.stop()
            return
