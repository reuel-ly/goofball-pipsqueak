import unittest
from unittest.mock import patch

from src.agent import prewarm as prewarm_llm
from src.config.llm import MODEL
from src.stt import prewarm as prewarm_stt
from src.tts import prewarm as prewarm_tts


class PrewarmTests(unittest.TestCase):
    @patch("src.agent.ollama.chat")
    def test_llm_prewarm(self, mock_chat):
        prewarm_llm()
        mock_chat.assert_called_once_with(
            model=MODEL,
            messages=[{"role": "user", "content": "hi"}],
            options={"num_predict": 1},
        )

    @patch("src.stt._get_model")
    def test_stt_prewarm(self, mock_get_model):
        prewarm_stt()
        mock_get_model.assert_called_once()

    @patch("src.tts.synthesize")
    @patch("src.tts._get_pipeline")
    def test_tts_prewarm(self, mock_pipeline, mock_synthesize):
        prewarm_tts()
        mock_pipeline.assert_called_once()
        mock_synthesize.assert_called_once_with(".")


if __name__ == "__main__":
    unittest.main()
