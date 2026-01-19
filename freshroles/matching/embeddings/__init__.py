"""Embedding providers."""

from freshroles.matching.embeddings.base import EmbeddingProvider
from freshroles.matching.embeddings.none import NoEmbeddingProvider
from freshroles.matching.embeddings.openai import OpenAIEmbeddingProvider
from freshroles.matching.embeddings.local import LocalEmbeddingProvider
from freshroles.matching.embeddings.ollama import OllamaEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "NoEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "LocalEmbeddingProvider",
    "OllamaEmbeddingProvider",
]
