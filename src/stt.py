import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

SR = 16000
DURATION = 5

_stt = None


def _get_model():
    global _stt
    if _stt is None:
        print("Loading Whisper base (int8, CPU)...")
        _stt = WhisperModel("base", device="cpu", compute_type="int8")
    return _stt


def listen(duration=DURATION, sr=SR, device=None):
    print(f"Listening for {duration}s...")
    audio = sd.rec(
        int(duration * sr),
        samplerate=sr,
        channels=1,
        dtype="float32",
        device=device,
    )
    sd.wait()
    segments, _ = _get_model().transcribe(audio.flatten(), language="en")
    return " ".join(s.text for s in segments).strip()
