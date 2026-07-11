import queue
import threading
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import sounddevice as sd

from src.tts import AudioPlayer, speak_phrases


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

    @patch("src.tts.AudioPlayer")
    @patch("src.tts._get_pipeline")
    def test_stop_event_aborts_playback_and_skips_synthesis(
        self, mock_get_pipeline, mock_player_cls
    ):
        pipeline_call, state = self._make_chunk_generator(count=2)
        mock_get_pipeline.return_value = pipeline_call

        mock_player = MagicMock()
        mock_player_cls.return_value = mock_player

        stop_event = threading.Event()
        stop_event.set()

        phrase_queue: queue.Queue[str | None] = queue.Queue()
        phrase_queue.put("Hello.")
        phrase_queue.put("World.")
        phrase_queue.put(None)

        speak_phrases(phrase_queue, stop_event=stop_event)

        mock_player.enqueue.assert_not_called()
        mock_player.stop.assert_called_once()
        mock_player.finish.assert_not_called()
        self.assertEqual(state["next_calls"], 0)


class AudioPlayerCallbackTests(unittest.TestCase):
    """Exercise the stream callback logic directly, without real audio."""

    def _run_callback(self, player: AudioPlayer, frames: int) -> np.ndarray:
        outdata = np.ones((frames, 1), dtype=np.float32)
        player._callback(outdata, frames, None, None)
        return outdata[:, 0]

    def test_chunks_play_in_order_with_silence_padding(self):
        player = AudioPlayer()
        player.enqueue(np.array([1.0, 2.0], dtype=np.float32))
        player.enqueue(np.array([3.0], dtype=np.float32))

        out = self._run_callback(player, 5)
        np.testing.assert_array_equal(
            out, np.array([1.0, 2.0, 3.0, 0.0, 0.0], dtype=np.float32)
        )

    def test_queue_underrun_pads_silence_without_stopping(self):
        player = AudioPlayer()
        out = self._run_callback(player, 4)
        np.testing.assert_array_equal(out, np.zeros(4, dtype=np.float32))

        player.enqueue(np.array([5.0], dtype=np.float32))
        out = self._run_callback(player, 2)
        np.testing.assert_array_equal(out, np.array([5.0, 0.0], dtype=np.float32))

    def test_sentinel_stops_after_audio_drained(self):
        player = AudioPlayer()
        player.enqueue(np.array([1.0, 2.0, 3.0], dtype=np.float32))
        player.finish()

        with self.assertRaises(sd.CallbackStop):
            self._run_callback(player, 8)

    def test_stop_discards_queued_audio(self):
        player = AudioPlayer()
        player._stream = MagicMock()
        player.enqueue(np.array([1.0, 2.0], dtype=np.float32))

        player.stop()

        self.assertTrue(player._queue.empty())
        self.assertTrue(player.wait(timeout=0))
        self.assertIsNone(player._stream)


if __name__ == "__main__":
    unittest.main()
