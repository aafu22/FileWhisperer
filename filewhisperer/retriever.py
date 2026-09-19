"""A small TF-IDF retriever.

No embedding API and no numpy/sklearn — just term frequencies, inverse
document frequency, and cosine similarity in plain Python. It's not as
strong as a real embedding model, but for a handful of documents it's fast,
dependency-light, and good enough to find the right chunks before handing
them to Claude.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .chunking import Chunk

_WORD_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "he", "in", "is", "it", "its", "of", "on", "or", "that", "the", "to",
    "was", "were", "will", "with", "this", "these", "those", "i", "you",
    "we", "they", "what", "which", "who", "how", "do", "does", "did",
}


def _tokenize(text: str) -> list[str]:
    words = _WORD_RE.findall(text.lower())
    return [w for w in words if w not in _STOPWORDS]


class TfidfRetriever:
    """Index a set of chunks, then rank them against a query."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._term_freqs: list[Counter] = [Counter(_tokenize(c.text)) for c in chunks]
        self._doc_freq: Counter = Counter()
        for tf in self._term_freqs:
            self._doc_freq.update(tf.keys())
        self._n_docs = max(len(chunks), 1)
        self._idf = {
            term: math.log((self._n_docs + 1) / (df + 1)) + 1
            for term, df in self._doc_freq.items()
        }
        self._vectors = [self._to_vector(tf) for tf in self._term_freqs]

    def _to_vector(self, tf: Counter) -> dict[str, float]:
        return {term: count * self._idf.get(term, 0.0) for term, count in tf.items()}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        shared = set(a) & set(b)
        if not shared:
            return 0.0
        dot = sum(a[t] * b[t] for t in shared)
        norm_a = math.sqrt(sum(v * v for v in a.values()))
        norm_b = math.sqrt(sum(v * v for v in b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def top_k(self, query: str, k: int = 6) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        query_tf = Counter(_tokenize(query))
        query_vec = self._to_vector(query_tf)
        scored = [
            (chunk, self._cosine(query_vec, vec))
            for chunk, vec in zip(self.chunks, self._vectors)
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        # Fall back to the first few chunks of each doc if nothing scored
        # (e.g. a one-word query with no term overlap).
        if all(score == 0 for _, score in scored):
            return scored[:k]
        return [pair for pair in scored if pair[1] > 0][:k]
