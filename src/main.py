from .agent import AgentSession


def _cli_on_event(event: dict) -> None:
    if event["type"] == "partial":
        print(f"\rYou: {event['text']}", end="", flush=True)
    elif event["type"] == "user":
        print()
    elif event["type"] == "assistant":
        print(f"Agent: {event['text']}")


def voice_loop():
    session = AgentSession(on_event=_cli_on_event)
    while True:
        input("\nPress Enter to speak...")
        session.listen_and_reply()


if __name__ == "__main__":
    voice_loop()
