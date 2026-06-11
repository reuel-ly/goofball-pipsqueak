import sounddevice as sd

from src.stt import listen

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
print(f"\nUsing mic [{mic_index}]: {mic['name']}\n")


def on_partial(text: str) -> None:
    print(f"\rPartial: {text}", end="", flush=True)


print("Speak now — partial captions appear while talking, stops after silence.\n")
result = listen(device=mic_index, on_partial=on_partial)
print()
print(result or "(no speech detected)")
