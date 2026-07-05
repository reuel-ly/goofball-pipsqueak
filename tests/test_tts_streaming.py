import queue
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from src.tts import speak_phrases


class TtsStreamingTests(unittest.TestCase):
    def _make_chunk_generator(self, count: int = 3):
        state = {"exhausted": False, "next_calls": 0}

        def pipeline_call(text, voice):
            def generator():
                for i in range(count):
                    state["next_calls"] += 1
                    yield (None, None, np.array([float(i)], dtype=np.float32))
                state["exhausted"] = True

            return generator()

        return pipeline_call, state

    @patch("src.tts.AudioPlayer")
    @patch("src.tts._get_pipeline")
    def test_first_chunk_enqueued_before_generator_exhausted(
        self, mock_get_pipeline, mock_player_cls
    ):
        state = {"exhausted": False, "first_enqueue_before_exhausted": None}

        def pipeline_call(text, voice):
            def generator():
                for i in range(3):
                    yield (None, None, np.array([float(i)], dtype=np.float32))
                state["exhausted"] = True

            return generator()

        mock_get_pipeline.return_value = pipeline_call

        mock_player = MagicMock()
        mock_player_cls.return_value = mock_player

        def track_enqueue(audio):
            if state["first_enqueue_before_exhausted"] is None:
                state["first_enqueue_before_exhausted"] = not state["exhausted"]

        mock_player.enqueue.side_effect = track_enqueue

        phrase_queue: queue.Queue[str | None] = queue.Queue()
        phrase_queue.put("Hello.")
        phrase_queue.put(None)

        speak_phrases(phrase_queue)

        self.assertTrue(state["first_enqueue_before_exhausted"])
        self.assertTrue(state["exhausted"])
        self.assertEqual(mock_player.enqueue.call_count, 3)

    @patch("src.tts.AudioPlayer")
    @patch("src.tts._get_pipeline")
    def test_on_first_phrase_fires_on_first_chunk(
        self, mock_get_pipeline, mock_player_cls
    ):
        pipeline_call, _ = self._make_chunk_generator(count=2)
        mock_get_pipeline.return_value = pipeline_call

        mock_player = MagicMock()
        mock_player_cls.return_value = mock_player

        callback_order: list[str] = []

        def on_first_phrase():
            callback_order.append("callback")

        def track_enqueue(audio):
            callback_order.append("enqueue")

        mock_player.enqueue.side_effect = track_enqueue

        phrase_queue: queue.Queue[str | None] = queue.Queue()
        phrase_queue.put("Hi.")
        phrase_queue.put(None)

        speak_phrases(phrase_queue, on_first_phrase=on_first_phrase)

        self.assertEqual(callback_order[0], "callback")
        self.assertEqual(callback_order[1], "enqueue")


if __name__ == "__main__":
    unittest.main()
