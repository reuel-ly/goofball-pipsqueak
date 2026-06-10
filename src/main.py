import ollama

from .config.agent import MODEL, SYSTEM

from .stt import listen
from .tts import speak


def voice_loop():
    history = [{"role": "system", "content": SYSTEM}]
    while True:
        input("\nPress Enter to speak...")
        text = listen()
        if not text:
            continue
        print(f"You: {text}")
        history.append({"role": "user", "content": text})
        resp = ollama.chat(model=MODEL, messages=history)
        reply = resp["message"]["content"]
        print(f"Agent: {reply}")
        history.append({"role": "assistant", "content": reply})
        speak(reply)


if __name__ == "__main__":
    voice_loop()
