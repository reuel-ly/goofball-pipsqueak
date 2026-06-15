import re
import time

ABBREVS = {"dr", "mr", "mrs", "ms", "prof", "sr", "jr", "vs", "etc", "u.s", "e.g", "i.e"}
_SENTENCE_BOUNDARY = re.compile(r"[.!?][\"']?\s*$")
_SOFT_BOUNDARY = re.compile(r"[,;:—]\s*$")
_WORD = re.compile(r"\S+")


class TextChunker:
    """Buffer streamed LLM tokens and emit speakable phrases."""

    def __init__(
        self,
        *,
        timeout_s: float = 0.25,
        min_sentence_words: int = 1,
        soft_clause_chars: int = 40,
        max_chars: int = 120,
        timeout_words: int = 3,
    ):
        self._buffer = ""
        self._timeout_s = timeout_s
        self._min_sentence_words = min_sentence_words
        self._soft_clause_chars = soft_clause_chars
        self._max_chars = max_chars
        self._timeout_words = timeout_words
        self._last_add = time.monotonic()

    @property
    def buffer(self) -> str:
        return self._buffer

    def add(self, token: str) -> list[str]:
        self._buffer += token
        self._last_add = time.monotonic()
        return self._drain()

    def check_timeout(self) -> list[str]:
        chunks = self._drain()
        if not self._buffer.strip():
            return chunks
        elapsed = time.monotonic() - self._last_add
        if elapsed >= self._timeout_s and self._word_count() >= self._timeout_words:
            chunks.append(self._buffer.strip())
            self._buffer = ""
        return chunks

    def flush(self) -> list[str]:
        chunks = self._drain()
        remainder = self._buffer.strip()
        if remainder:
            chunks.append(remainder)
            self._buffer = ""
        return chunks

    def _drain(self) -> list[str]:
        chunks: list[str] = []
        while self._buffer.strip():
            self._buffer = self._buffer.lstrip()

            if self._has_sentence_boundary():
                chunk_end = len(self._buffer)
            elif self._has_soft_boundary():
                chunk_end = len(self._buffer)
            elif len(self._buffer) >= self._max_chars:
                chunk_end = self._max_chars
                ws = self._buffer.rfind(" ", 0, self._max_chars)
                if ws > 0:
                    chunk_end = ws
            else:
                break

            phrase = self._buffer[:chunk_end].strip()
            if phrase:
                chunks.append(phrase)
            self._buffer = self._buffer[chunk_end:]
        return chunks

    def _has_sentence_boundary(self) -> bool:
        return (
            _SENTENCE_BOUNDARY.search(self._buffer) is not None
            and self._word_count() >= self._min_sentence_words
            and not self._ends_with_abbreviation()
        )

    def _has_soft_boundary(self) -> bool:
        return (
            _SOFT_BOUNDARY.search(self._buffer) is not None
            and len(self._buffer) >= self._soft_clause_chars
        )

    def _word_count(self) -> int:
        return len(_WORD.findall(self._buffer))

    def _ends_with_abbreviation(self) -> bool:
        words = self._buffer.rstrip(".!?\"' ").split()
        if not words:
            return False
        return words[-1].lower() in ABBREVS
