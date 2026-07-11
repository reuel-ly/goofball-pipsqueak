SR = 16000
FRAME_MS = 30
FRAME_SAMPLES = SR * FRAME_MS // 1000

VAD_AGGRESSIVENESS = 2
SILENCE_MS = 700
ENABLE_PARTIALS = True
PARTIAL_INTERVAL_S = 1.5
MIN_SPEECH_MS = 300
MAX_UTTERANCE_S = 30
IDLE_TIMEOUT_S = 10.0
LEVEL_INTERVAL_S = 0.1

# English-only model: strictly better than multilingual "base" when
# LANGUAGE is hardcoded to English, and slightly faster.
MODEL = "base.en"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

LANGUAGE = "en"
VAD_FILTER = False
WITHOUT_TIMESTAMPS = True
