"""Matching module."""

from freshroles.matching.scorer import Scorer
from freshroles.matching.keyword import KeywordScorer, RecencyScorer
from freshroles.matching.dedup import Deduplicator, simhash, simhash_similarity
from freshroles.matching.vector_matcher import VectorMatcher, VectorMatchResult
from freshroles.matching.embeddings import (
    EmbeddingProvider,
    NoEmbeddingProvider,
    OpenAIEmbeddingProvider,
    LocalEmbeddingProvider,
    OllamaEmbeddingProvider,
)

__all__ = [
    "Scorer",
    "KeywordScorer",
    "RecencyScorer",
    "Deduplicator",
    "simhash",
    "simhash_similarity",
    "VectorMatcher",
    "VectorMatchResult",
    "EmbeddingProvider",
    "NoEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "LocalEmbeddingProvider",
    "OllamaEmbeddingProvider",
]
