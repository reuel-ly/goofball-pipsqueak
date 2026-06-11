import queue
import time
from collections.abc import Callable

import numpy as np
import sounddevice as sd
import webrtcvad
from faster_whisper import WhisperModel

from .config.stt import (
    COMPUTE_TYPE,
    DEVICE,
    FRAME_MS,
    FRAME_SAMPLES,
    LANGUAGE,
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


def listen(device=None, on_partial: Callable[[str], None] | None = None) -> str:
    """Stream mic audio, emit partial captions while speaking, return final transcript."""
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
    last_partial_time = 0.0

    silence_frame_limit = SILENCE_MS // FRAME_MS
    min_speech_frames = MIN_SPEECH_MS // FRAME_MS
    max_frames = MAX_UTTERANCE_S * 1000 // FRAME_MS

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
            try:
                frame = audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            is_speech = vad.is_speech(frame.tobytes(), SR)

            if state == "idle":
                if not is_speech:
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

            now = time.monotonic()
            if now - last_partial_time >= PARTIAL_INTERVAL_S:
                text = _transcribe(np.concatenate(utterance_frames))
                if text:
                    on_partial(text)
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

    if speech_frames < min_speech_frames:
        print()
        return ""

    final = _transcribe(np.concatenate(utterance_frames))
    print()
    return final
