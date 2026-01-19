"""No-embedding provider (baseline only)."""

from freshroles.matching.embeddings.base import EmbeddingProvider


class NoEmbeddingProvider(EmbeddingProvider):
    """
    Placeholder provider that returns zero vectors.
    
    Used when embeddings are not available, falling back
    to keyword-only matching.
    """
    
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return zero vectors for all texts."""
        return [[0.0] * self.dimension for _ in texts]
    
    def similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Always returns 0.5 (neutral) since no real embeddings."""
        return 0.5
