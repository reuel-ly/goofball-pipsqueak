import queue
import threading
import time
from collections.abc import Callable

import numpy as np
import sounddevice as sd
import webrtcvad
from faster_whisper import WhisperModel

from .config.stt import (
    COMPUTE_TYPE,
    DEVICE,
    ENABLE_PARTIALS,
    FRAME_MS,
    FRAME_SAMPLES,
    IDLE_TIMEOUT_S,
    LANGUAGE,
    LEVEL_INTERVAL_S,
    MAX_UTTERANCE_S,
    MIN_SPEECH_MS,
    MODEL,
    PARTIAL_INTERVAL_S,
    SILENCE_MS,
    SR,
    VAD_AGGRESSIVENESS,
    VAD_FILTER,
    WITHOUT_TIMESTAMPS,
)

_stt = None


def _get_model():
    global _stt
    if _stt is None:
        print(f"Loading Whisper {MODEL} ({COMPUTE_TYPE}, {DEVICE.upper()})...")
        _stt = WhisperModel(MODEL, device=DEVICE, compute_type=COMPUTE_TYPE)
    return _stt


def prewarm() -> None:
    _get_model()


def _int16_to_float32(pcm: np.ndarray) -> np.ndarray:
    return pcm.astype(np.float32) / 32768.0


def _transcribe(pcm_int16: np.ndarray) -> str:
    if len(pcm_int16) == 0:
        return ""
    segments, _ = _get_model().transcribe(
        _int16_to_float32(pcm_int16),
        language=LANGUAGE,
        vad_filter=VAD_FILTER,
        without_timestamps=WITHOUT_TIMESTAMPS,
    )
    return " ".join(s.text for s in segments).strip()


def _default_on_partial(text: str) -> None:
    print(f"\rListening: {text}   ", end="", flush=True)


class _PartialWorker:
    """Transcribe utterance snapshots on a single background thread.

    Only the latest snapshot is kept: if a transcription is still running
    when a new snapshot arrives, the old pending one is replaced. The
    capture loop is never blocked and work never queues up (the naive
    approach re-transcribed the whole utterance every tick, O(n^2)).

    Tracks how many frames the last completed transcription covered, so
    the caller can reuse it as the final transcript when it already spans
    all speech frames.
    """

    def __init__(self, on_partial: Callable[[str], None]):
        self._on_partial = on_partial
        self._lock = threading.Lock()
        self._pending: list[np.ndarray] | None = None
        self._generation = 0
        self._wakeup = threading.Event()
        self._stop = threading.Event()
        self.covered_frames = 0
        self.text = ""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def request(self, frames: list[np.ndarray]) -> None:
        with self._lock:
            self._pending = frames
        self._wakeup.set()

    def reset(self) -> None:
        """Discard state from an utterance that turned out to be a false start."""
        with self._lock:
            self._generation += 1
            self._pending = None
            self.covered_frames = 0
            self.text = ""

    def close(self) -> None:
        """Stop the worker, waiting for any in-flight transcription."""
        self._stop.set()
        self._wakeup.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wakeup.wait()
            self._wakeup.clear()
            if self._stop.is_set():
                break
            with self._lock:
                snapshot = self._pending
                generation = self._generation
                self._pending = None
            if snapshot is None:
                continue
            text = _transcribe(np.concatenate(snapshot))
            with self._lock:
                if generation != self._generation:
                    continue
                self.covered_frames = len(snapshot)
                self.text = text
            if text and not self._stop.is_set():
                self._on_partial(text)


def listen(
    device=None,
    on_partial: Callable[[str], None] | None = None,
    on_level: Callable[[float], None] | None = None,
    stop_event: threading.Event | None = None,
) -> str:
    """Stream mic audio, emit partial captions and mic levels while speaking,
    and return the final transcript.

    Returns "" when cancelled via stop_event, when no speech is heard for
    IDLE_TIMEOUT_S, or when the captured speech is too short.
    """
    if on_partial is None:
        on_partial = _default_on_partial

    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
    audio_queue: queue.Queue[np.ndarray] = queue.Queue()

    def callback(indata, frames, time_info, status):
        if status:
            print(status)
        audio_queue.put(indata[:, 0].copy())

    utterance_frames: list[np.ndarray] = []
    state = "idle"
    silence_frames = 0
    speech_frames = 0
    idle_start = time.monotonic()
    last_partial_time = 0.0
    last_level_time = 0.0
    cancelled = False

    silence_frame_limit = SILENCE_MS // FRAME_MS
    min_speech_frames = MIN_SPEECH_MS // FRAME_MS
    max_frames = MAX_UTTERANCE_S * 1000 // FRAME_MS

    partial_worker = _PartialWorker(on_partial) if ENABLE_PARTIALS else None

    print("Listening... (speak now)")

    with sd.InputStream(
        samplerate=SR,
        channels=1,
        dtype="int16",
        blocksize=FRAME_SAMPLES,
        device=device,
        callback=callback,
    ):
        while True:
            if stop_event is not None and stop_event.is_set():
                cancelled = True
                break

            try:
                frame = audio_queue.get(timeout=0.1)
            except queue.Empty:
                if (
                    state == "idle"
                    and time.monotonic() - idle_start >= IDLE_TIMEOUT_S
                ):
                    break
                continue

            if on_level is not None:
                now = time.monotonic()
                if now - last_level_time >= LEVEL_INTERVAL_S:
                    rms = float(np.sqrt(np.mean(_int16_to_float32(frame) ** 2)))
                    on_level(rms)
                    last_level_time = now

            is_speech = vad.is_speech(frame.tobytes(), SR)

            if state == "idle":
                if not is_speech:
                    if time.monotonic() - idle_start >= IDLE_TIMEOUT_S:
                        break
                    continue
                state = "speaking"
                utterance_frames = [frame]
                speech_frames = 1
                silence_frames = 0
                last_partial_time = time.monotonic()
                continue

            utterance_frames.append(frame)
            if is_speech:
                speech_frames += 1
                silence_frames = 0
            else:
                silence_frames += 1

            if partial_worker is not None:
                now = time.monotonic()
                if now - last_partial_time >= PARTIAL_INTERVAL_S:
                    partial_worker.request(list(utterance_frames))
                    last_partial_time = now

            if len(utterance_frames) >= max_frames:
                break

            if silence_frames >= silence_frame_limit:
                if speech_frames >= min_speech_frames:
                    break
                state = "idle"
                utterance_frames = []
                speech_frames = 0
                silence_frames = 0
                idle_start = time.monotonic()
                if partial_worker is not None:
                    partial_worker.reset()

    if partial_worker is not None:
        partial_worker.close()

    if cancelled or speech_frames < min_speech_frames:
        print()
        return ""

    # If the last completed partial already covers every frame up to the
    # trailing silence, it is the full transcript -- skip re-transcribing
    # the whole utterance after the endpoint.
    if (
        partial_worker is not None
        and partial_worker.covered_frames
        >= len(utterance_frames) - silence_frame_limit
    ):
        print()
        return partial_worker.text

    final = _transcribe(np.concatenate(utterance_frames))
    print()
    return final
