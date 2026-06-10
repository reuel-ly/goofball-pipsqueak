import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel

SR = 16000
DURATION = 5

# Step 1: check mic device index
print("=== Audio devices ===\n")
print(sd.query_devices())
print()

inputs = [
    (i, d)
    for i, d in enumerate(sd.query_devices())
    if d["max_input_channels"] > 0
]
for idx, dev in inputs:
    default = " (default)" if idx == sd.default.device[0] else ""
    print(f"  [{idx}] {dev['name']}{default}")

mic_index = sd.default.device[0]
mic = sd.query_devices(mic_index)
print(f"\nRecording from mic [{mic_index}]: {mic['name']}\n")

# Step 2: load base model with int8 quantization (CPU)
print("Loading Whisper base (int8, CPU)...")
stt = WhisperModel("base", device="cpu", compute_type="int8")
print("Model ready.\n")

# Step 3: record 5 seconds and transcribe locally (no cloud)
# Phase 7: upgrade to VAD-based auto-stop listening with webrtcvad.


def listen(duration=DURATION, sr=SR, device=mic_index):
    print(f"Listening for {duration}s...")
    audio = sd.rec(
        int(duration * sr),
        samplerate=sr,
        channels=1,
        dtype="float32",
        device=device,
    )
    sd.wait()
    segments, _ = stt.transcribe(audio.flatten(), language="en")
    return " ".join(s.text for s in segments).strip()


print(listen() or "(no speech detected)")
