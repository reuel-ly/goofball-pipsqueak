import sounddevice as sd
import numpy as np

SR = 16000
DURATION = 2


def list_devices():
    print("=== Audio devices ===\n")
    print(sd.query_devices())
    print()

    inputs = [
        (i, d)
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]

    print(f"Input devices found: {len(inputs)}")
    for idx, dev in inputs:
        default = " (default)" if idx == sd.default.device[0] else ""
        print(f"  [{idx}] {dev['name']}{default}")
        print(f"       channels={dev['max_input_channels']}, sr={dev['default_samplerate']}")

    return inputs


def test_default_mic(duration=DURATION, sr=SR):
    default_in = sd.default.device[0]
    if default_in is None or default_in < 0:
        print("\nNo default input device configured.")
        return False

    dev = sd.query_devices(default_in)
    print(f"\n=== Recording from default mic [{default_in}] {dev['name']} ===")
    print(f"Recording {duration}s at {sr} Hz...")

    try:
        audio = sd.rec(int(duration * sr), samplerate=sr, channels=1, dtype="float32")
        sd.wait()
    except sd.PortAudioError as e:
        print(f"Recording failed: {e}")
        return False

    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(audio**2)))
    print(f"Peak amplitude: {peak:.4f}")
    print(f"RMS level:      {rms:.4f}")

    if peak < 0.001:
        print("Mic detected but signal is very quiet (check mute/gain or speak during recording).")
        return True

    print("Mic is working — audio captured successfully.")
    return True


if __name__ == "__main__":
    inputs = list_devices()

    if not inputs:
        print("\nNo microphone detected.")
        raise SystemExit(1)

    ok = test_default_mic()
    raise SystemExit(0 if ok else 1)
