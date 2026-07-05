import time
import unittest

from src.chunker import TextChunker


class TextChunkerTests(unittest.TestCase):
    def test_one_word_sentence_flushes_on_period(self):
        chunker = TextChunker()
        self.assertEqual(chunker.add("Hi."), ["Hi."])
        self.assertEqual(chunker.buffer, "")

    def test_four_word_sentence_flushes_on_period(self):
        chunker = TextChunker()
        self.assertEqual(chunker.add("This has four words."), ["This has four words."])
        self.assertEqual(chunker.buffer, "")

    def test_sentence_flushes_on_question_mark(self):
        chunker = TextChunker()
        self.assertEqual(
            chunker.add("Can you hear me?"),
            ["Can you hear me?"],
        )

    def test_sentence_flushes_on_exclamation_with_quote(self):
        chunker = TextChunker()
        self.assertEqual(
            chunker.add("That sounds very good!'"),
            ["That sounds very good!'"],
        )

    def test_abbreviation_does_not_flush(self):
        chunker = TextChunker()
        self.assertEqual(chunker.add("Please ask Prof."), [])
        self.assertEqual(chunker.buffer, "Please ask Prof.")

    def test_soft_clause_under_threshold_stays_buffered(self):
        chunker = TextChunker()
        self.assertEqual(chunker.add("This is a short clause,"), [])
        self.assertEqual(chunker.buffer, "This is a short clause,")

    def test_soft_clause_at_threshold_flushes(self):
        chunker = TextChunker(soft_clause_chars=20)
        self.assertEqual(
            chunker.add("This clause is long enough,"),
            ["This clause is long enough,"],
        )

    def test_soft_clause_flushes_on_em_dash(self):
        chunker = TextChunker(soft_clause_chars=20)
        self.assertEqual(
            chunker.add("This clause is long enough—"),
            ["This clause is long enough—"],
        )

    def test_hard_length_ceiling_flushes_without_punctuation(self):
        chunker = TextChunker(max_chars=12)
        self.assertEqual(chunker.add("abcdefghijklmnop"), ["abcdefghijkl"])
        self.assertEqual(chunker.buffer, "mnop")

    def test_hard_length_prefers_last_whitespace(self):
        chunker = TextChunker(max_chars=12)
        self.assertEqual(chunker.add("hello world foo"), ["hello world"])
        self.assertEqual(chunker.buffer, "foo")

    def test_timeout_flushes_only_with_enough_words(self):
        chunker = TextChunker(timeout_s=0.1, timeout_words=5)
        chunker.add("one two three four five")
        time.sleep(0.15)
        self.assertEqual(chunker.check_timeout(), ["one two three four five"])

    def test_timeout_skips_too_few_words(self):
        chunker = TextChunker(timeout_s=0.1, timeout_words=5)
        chunker.add("one two three four")
        time.sleep(0.15)
        self.assertEqual(chunker.check_timeout(), [])

    def test_flush_emits_one_word_remainder(self):
        chunker = TextChunker()
        chunker.add("Still")
        self.assertEqual(chunker.flush(), ["Still"])

    def test_timeout_ignores_empty_buffer(self):
        chunker = TextChunker(timeout_s=0.1)
        time.sleep(0.15)
        self.assertEqual(chunker.check_timeout(), [])


if __name__ == "__main__":
    unittest.main()
