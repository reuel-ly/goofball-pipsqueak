import os, time
import torch
from kokoro import KPipeline

test_text = "Your first email is from John about the project deadline on Friday."

for n_threads in [1, 2, 4, 8]:
    os.environ["OMP_NUM_THREADS"] = str(n_threads)
    torch.set_num_threads(n_threads)

    tts = KPipeline(lang_code="a")  # reload with new setting
    _ = [a for _, _, a in tts("warmup", voice="af_heart")]  # warm up

    t = time.time()
    for _ in range(3):  # average over 3 runs
        _ = [a for _, _, a in tts(test_text, voice="af_heart")]
    avg = (time.time() - t) / 3

    print(f"  threads={n_threads}  avg={avg:.3f}s")
