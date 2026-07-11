import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from src.config.stt import FRAME_SAMPLES
from src.stt import _PartialWorker, listen

SPEECH_FRAME = np.full(FRAME_SAMPLES, 1000, dtype=np.int16)
SILENCE_FRAME = np.zeros(FRAME_SAMPLES, dtype=np.int16)


class FakeInputStream:
    """Feeds a scripted list of frames into the capture callback on enter."""

    script: list[np.ndarray] = []

    def __init__(self, *, callback=None, **kwargs):
        self._callback = callback

    def __enter__(self):
        for frame in FakeInputStream.script:
            self._callback(frame.reshape(-1, 1), len(frame), None, None)
        return self

    def __exit__(self, *args):
        return False


class FakeVad:
    def __init__(self, *args):
        pass

    def is_speech(self, buf: bytes, sr: int) -> bool:
        return any(buf)


def _patch_audio(script: list[np.ndarray]):
    FakeInputStream.script = script
    return [
        patch("src.stt.sd.InputStream", FakeInputStream),
        patch("src.stt.webrtcvad.Vad", FakeVad),
        patch("src.stt.IDLE_TIMEOUT_S", 0.3),
    ]


class ListenTests(unittest.TestCase):
    def _listen(self, script, **kwargs):
        patches = _patch_audio(script)
        for p in patches:
            p.start()
        try:
            return listen(**kwargs)
        finally:
            for p in patches:
                p.stop()

    @patch("src.stt.ENABLE_PARTIALS", False)
    @patch("src.stt._transcribe")
    def test_stop_event_cancels_immediately(self, mock_transcribe):
        stop_event = threading.Event()
        stop_event.set()

        result = self._listen([SPEECH_FRAME] * 20, stop_event=stop_event)

        self.assertEqual(result, "")
        mock_transcribe.assert_not_called()

    @patch("src.stt.ENABLE_PARTIALS", False)
    @patch("src.stt._transcribe")
    def test_idle_timeout_returns_empty(self, mock_transcribe):
        result = self._listen([])

        self.assertEqual(result, "")
        mock_transcribe.assert_not_called()

    @patch("src.stt.ENABLE_PARTIALS", False)
    @patch("src.stt._transcribe", return_value="hello world")
    def test_speech_then_silence_returns_final_transcript(self, mock_transcribe):
        levels: list[float] = []
        script = [SPEECH_FRAME] * 15 + [SILENCE_FRAME] * 30

        result = self._listen(script, on_level=levels.append)

        self.assertEqual(result, "hello world")
        self.assertTrue(levels)
        self.assertTrue(all(isinstance(v, float) for v in levels))

    @patch("src.stt.ENABLE_PARTIALS", False)
    @patch("src.stt._transcribe")
    def test_too_short_speech_returns_empty(self, mock_transcribe):
        # 3 speech frames is below MIN_SPEECH_MS; then silence, then idle timeout.
        script = [SPEECH_FRAME] * 3 + [SILENCE_FRAME] * 30

        result = self._listen(script)

        self.assertEqual(result, "")
        mock_transcribe.assert_not_called()


class PartialWorkerTests(unittest.TestCase):
    @patch("src.stt._transcribe", return_value="partial text")
    def test_processes_snapshot_and_reports_coverage(self, mock_transcribe):
        partials: list[str] = []
        worker = _PartialWorker(partials.append)

        frames = [SPEECH_FRAME] * 5
        worker.request(list(frames))

        deadline = time.monotonic() + 2.0
        while worker.covered_frames == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        worker.close()

        self.assertEqual(worker.covered_frames, 5)
        self.assertEqual(worker.text, "partial text")
        self.assertEqual(partials, ["partial text"])

    def test_reset_discards_stale_in_flight_result(self):
        release = threading.Event()

        def slow_transcribe(audio):
            release.wait(timeout=2.0)
            return "stale text"

        with patch("src.stt._transcribe", side_effect=slow_transcribe):
            worker = _PartialWorker(lambda text: None)
            worker.request([SPEECH_FRAME] * 5)

            # Wait until the worker picks up the snapshot, then invalidate it.
            deadline = time.monotonic() + 2.0
            while worker._pending is not None and time.monotonic() < deadline:
                time.sleep(0.01)
            worker.reset()
            release.set()
            worker.close()

        self.assertEqual(worker.covered_frames, 0)
        self.assertEqual(worker.text, "")


if __name__ == "__main__":
    unittest.main()
