"""Ollama embedding provider for local LLM embeddings."""

from typing import Any
import numpy as np

import httpx

from freshroles.matching.embeddings.base import EmbeddingProvider


class OllamaEmbeddingProvider(EmbeddingProvider):
    """
    Local embedding provider using Ollama.
    
    Ollama runs LLMs locally with GPU acceleration.
    Install Ollama from: https://ollama.ai
    
    Recommended embedding models:
    - nomic-embed-text (good quality, 768 dim)
    - mxbai-embed-large (high quality, 1024 dim)
    - all-minilm (fast, 384 dim)
    """
    
    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
    ):
        """
        Initialize Ollama embedding provider.
        
        Args:
            model: Ollama embedding model name.
            base_url: Ollama server URL.
        """
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings using Ollama's local API.
        
        Args:
            texts: List of texts to embed.
            
        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []
        
        client = await self._get_client()
        embeddings = []
        
        for text in texts:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            response.raise_for_status()
            data = response.json()
            embeddings.append(data["embedding"])
        
        return embeddings
    
    def similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        v1 = np.array(vec1, dtype=np.float32)
        v2 = np.array(vec2, dtype=np.float32)
        
        dot = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot / (norm1 * norm2))
    
    async def is_available(self) -> bool:
        """Check if Ollama server is running and model is available."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                return any(m.get("name", "").startswith(self.model) for m in models)
        except Exception:
            pass
        return False
    
    async def pull_model(self) -> bool:
        """Pull the embedding model if not already downloaded."""
        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/api/pull",
                json={"name": self.model},
                timeout=300.0,  # Models can take time to download
            )
            return response.status_code == 200
        except Exception:
            return False
