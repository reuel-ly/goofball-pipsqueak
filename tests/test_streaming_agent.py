import queue
import threading
import unittest
from unittest.mock import patch

from src.agent import AgentSession


class StreamingAgentTests(unittest.TestCase):
    def test_generate_reply_emits_partials_before_completion(self):
        events: list[dict] = []
        session = AgentSession(on_event=events.append)
        tokens = ["Hel", "lo", ". ", "Good", "bye", "."]

        with patch.object(session, "_stream_chat", return_value=iter(tokens)):
            reply = session._generate_reply(speak_reply=False)

        self.assertEqual(reply, "Hello. Goodbye.")
        deltas = [e["delta"] for e in events if e["type"] == "assistant_partial"]
        self.assertEqual("".join(deltas), "Hello. Goodbye.")
        self.assertGreater(len(deltas), 1)

    def test_tts_receives_first_phrase_before_stream_ends(self):
        session = AgentSession()
        stream_index = {"i": 0}
        stream_done = threading.Event()
        tokens = list("This is first sentence. And more text here.")
        phrase_put_indices: list[int] = []
        original_put = queue.Queue.put

        def slow_stream():
            for i, token in enumerate(tokens):
                stream_index["i"] = i
                yield token
            stream_done.set()

        def track_put(self, item, block=True, timeout=None):
            if item is not None and not stream_done.is_set():
                phrase_put_indices.append(stream_index["i"])
            return original_put(self, item, block=block, timeout=timeout)

        def drain_phrases(phrase_queue, *, on_first_phrase=None, stop_event=None):
            while True:
                item = phrase_queue.get(timeout=5)
                if item is None:
                    break
                if on_first_phrase:
                    on_first_phrase()
                    on_first_phrase = None

        with (
            patch.object(session, "_stream_chat", side_effect=slow_stream),
            patch("src.agent.speak_phrases", side_effect=drain_phrases),
            patch.object(queue.Queue, "put", track_put),
        ):
            session._generate_reply(speak_reply=True)

        self.assertTrue(phrase_put_indices)
        self.assertLess(phrase_put_indices[0], len(tokens) - 1)

    def test_short_reply_reaches_phrase_queue_before_stream_ends(self):
        session = AgentSession()
        stream_index = {"i": 0}
        stream_done = threading.Event()
        tokens = ["Yes", ".", " More", " here", "."]
        phrase_put_indices: list[int] = []
        original_put = queue.Queue.put

        def slow_stream():
            for i, token in enumerate(tokens):
                stream_index["i"] = i
                yield token
            stream_done.set()

        def track_put(self, item, block=True, timeout=None):
            if item is not None and not stream_done.is_set():
                phrase_put_indices.append(stream_index["i"])
            return original_put(self, item, block=block, timeout=timeout)

        def drain_phrases(phrase_queue, *, on_first_phrase=None, stop_event=None):
            while True:
                item = phrase_queue.get(timeout=5)
                if item is None:
                    break
                if on_first_phrase:
                    on_first_phrase()
                    on_first_phrase = None

        with (
            patch.object(session, "_stream_chat", side_effect=slow_stream),
            patch("src.agent.speak_phrases", side_effect=drain_phrases),
            patch.object(queue.Queue, "put", track_put),
        ):
            session._generate_reply(speak_reply=True)

        self.assertTrue(phrase_put_indices)
        self.assertLess(phrase_put_indices[0], len(tokens) - 1)

    def test_speak_reply_transitions_to_speaking(self):
        events: list[dict] = []
        session = AgentSession(on_event=events.append)
        tokens = ["Hi."]

        def fake_speak_phrases(phrase_queue, *, on_first_phrase=None, stop_event=None):
            while True:
                item = phrase_queue.get(timeout=5)
                if item is None:
                    break
                if on_first_phrase:
                    on_first_phrase()
                    on_first_phrase = None

        with (
            patch.object(session, "_stream_chat", return_value=iter(tokens)),
            patch("src.agent.speak_phrases", side_effect=fake_speak_phrases),
        ):
            session._generate_reply(speak_reply=True)

        states = [e["state"] for e in events if e.get("type") == "status"]
        self.assertIn("speaking", states)

    def test_request_stop_interrupts_generation(self):
        events: list[dict] = []
        session = AgentSession(on_event=events.append)
        spoken_phrases: list[str] = []

        def stream_then_stop():
            yield "First sentence. "
            session.request_stop()
            yield "Never emitted. "
            yield "Also never emitted."

        def fake_speak_phrases(phrase_queue, *, on_first_phrase=None, stop_event=None):
            while True:
                item = phrase_queue.get(timeout=5)
                if item is None:
                    break
                if stop_event is not None and stop_event.is_set():
                    continue
                spoken_phrases.append(item)

        with (
            patch.object(session, "_stream_chat", side_effect=stream_then_stop),
            patch("src.agent.speak_phrases", side_effect=fake_speak_phrases),
        ):
            reply = session._generate_reply(speak_reply=True)

        self.assertEqual(reply, "First sentence. ")
        deltas = [e["delta"] for e in events if e["type"] == "assistant_partial"]
        self.assertEqual("".join(deltas), "First sentence. ")
        self.assertNotIn("Never emitted. ", spoken_phrases)

    def test_trim_history_keeps_system_and_recent_turns(self):
        session = AgentSession()
        for i in range(10):
            session.history.append({"role": "user", "content": f"user-{i}"})
            session.history.append({"role": "assistant", "content": f"assistant-{i}"})

        session._trim_history()

        self.assertEqual(session.history[0]["role"], "system")
        self.assertEqual(len(session.history), 1 + 6)
        self.assertEqual(session.history[-2]["content"], "user-9")
        self.assertEqual(session.history[-1]["content"], "assistant-9")


if __name__ == "__main__":
    unittest.main()
