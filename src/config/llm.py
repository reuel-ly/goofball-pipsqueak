SYSTEM = "You are a voice assistant. Keep replies to 1-2 sentences."
MODEL = "gemma4:e2b-it-qat"
NUM_THREADS = 6
NUM_GPU = 999  # max layers on GPU; Ollama clamps to model depth
MAX_HISTORY_TURNS = 3
THINK = False


def ollama_options(**overrides) -> dict:
    opts = {"num_thread": NUM_THREADS, "num_gpu": NUM_GPU}
    opts.update(overrides)
    return opts
