from kokoro import KPipeline
import sounddevice as sd
import numpy as np

tts = KPipeline(lang_code="a")  # 'a' = American English

def speak(text):
    chunks = [a for _, _, a in tts(text, voice="af_heart")]
    sd.play(np.concatenate(chunks), samplerate=24000)
    sd.wait()

speak("Voice agent is online and ready.")