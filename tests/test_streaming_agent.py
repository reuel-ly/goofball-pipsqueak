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
        partial_texts = [e["text"] for e in events if e["type"] == "assistant_partial"]
        self.assertEqual(partial_texts[-1], "Hello. Goodbye.")
        self.assertLess(partial_texts[0], partial_texts[-1])

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

        def drain_phrases(phrase_queue, *, on_first_phrase=None):
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

        def drain_phrases(phrase_queue, *, on_first_phrase=None):
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

        def fake_speak_phrases(phrase_queue, *, on_first_phrase=None):
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


if __name__ == "__main__":
    unittest.main()
