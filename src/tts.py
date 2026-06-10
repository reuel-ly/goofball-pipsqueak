import numpy as np
import sounddevice as sd
from kokoro import KPipeline

_tts = None


def _get_pipeline():
    global _tts
    if _tts is None:
        _tts = KPipeline(lang_code="a")
    return _tts


def speak(text):
    chunks = [a for _, _, a in _get_pipeline()(text, voice="af_heart")]
    sd.play(np.concatenate(chunks), samplerate=24000)
    sd.wait()
