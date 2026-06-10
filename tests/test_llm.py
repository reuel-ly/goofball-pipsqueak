import ollama

# Basic response
resp = ollama.chat(
    model="gemma4:e2b-it-qat",
    messages=[{"role": "user", "content": "Say hi in one sentence."}]
)
print(resp["message"]["content"])

# Streaming — use this later for low-latency TTS
for chunk in ollama.chat(
        model="gemma4:e2b-it-qat",
        messages=[{"role": "user", "content": "Count to 5."}],
        stream=True):
    print(chunk["message"]["content"], end="", flush=True)