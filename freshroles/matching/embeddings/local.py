"""Local embedding provider using sentence-transformers with GPU acceleration."""

from typing import Any
import numpy as np

from freshroles.matching.embeddings.base import EmbeddingProvider


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Local GPU-accelerated embedding provider using sentence-transformers.
    
    Runs entirely locally on your GPU (RTX 5070), no API key required.
    Uses all-MiniLM-L6-v2 by default (fast and good quality).
    """
    
    # Recommended models for GPU
    MODELS = {
        "fast": "all-MiniLM-L6-v2",           # 384 dim, fastest
        "balanced": "all-mpnet-base-v2",       # 768 dim, good quality
        "quality": "all-MiniLM-L12-v2",        # 384 dim, better quality
        "e5": "intfloat/e5-small-v2",          # 384 dim, excellent for search
        "bge": "BAAI/bge-small-en-v1.5",       # 384 dim, great for retrieval
    }
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str = "cuda",  # Use GPU by default
        batch_size: int = 32,
    ):
        """
        Initialize local GPU embedding provider.
        
        Args:
            model_name: HuggingFace model name or preset ("fast", "balanced", "quality", "e5", "bge").
            device: Device to run on ("cuda" for GPU, "cpu" for CPU).
            batch_size: Batch size for encoding (higher = faster but more VRAM).
        """
        # Allow preset names
        self.model_name = self.MODELS.get(model_name, model_name)
        self.device = device
        self.batch_size = batch_size
        self._model: Any = None
    
    def _get_model(self):
        """Lazy load the model onto GPU."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                import torch
                
                # Check if CUDA is available
                if self.device == "cuda" and not torch.cuda.is_available():
                    print("CUDA not available, falling back to CPU")
                    self.device = "cpu"
                
                # Load model onto specified device
                self._model = SentenceTransformer(self.model_name, device=self.device)
                
                # Enable half precision for faster inference on GPU
                if self.device == "cuda":
                    self._model = self._model.half()
                    print(f"Loaded {self.model_name} on GPU with FP16")
                else:
                    print(f"Loaded {self.model_name} on CPU")
                    
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers torch"
                )
        return self._model
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings locally using GPU-accelerated sentence-transformers.
        
        Args:
            texts: List of texts to embed.
            
        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []
        
        model = self._get_model()
        
        # Encode with GPU optimization
        embeddings = model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 100,
            normalize_embeddings=True,  # L2 normalize for cosine similarity
            batch_size=self.batch_size,
        )
        
        return embeddings.astype(np.float32).tolist()
    
    def similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """
        Compute cosine similarity between normalized vectors.
        
        Since vectors are L2 normalized, dot product = cosine similarity.
        """
        v1 = np.array(vec1, dtype=np.float32)
        v2 = np.array(vec2, dtype=np.float32)
        
        return float(np.dot(v1, v2))
    
    async def embed_and_rank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[tuple[int, float]]:
        """
        Embed query and documents, return ranked similarity scores.
        
        Args:
            query: The query text (e.g., user profile).
            documents: List of document texts (e.g., job descriptions).
            top_k: Return only top K results (None = all).
            
        Returns:
            List of (index, similarity) tuples, sorted by similarity descending.
        """
        if not documents:
            return []
        
        # Embed all at once for GPU efficiency
        all_texts = [query] + documents
        embeddings = await self.embed(all_texts)
        
        query_emb = np.array(embeddings[0], dtype=np.float32)
        doc_embs = np.array(embeddings[1:], dtype=np.float32)
        
        # Batch similarity computation (GPU-friendly)
        similarities = np.dot(doc_embs, query_emb)
        
        # Get sorted indices
        sorted_indices = np.argsort(similarities)[::-1]
        
        if top_k:
            sorted_indices = sorted_indices[:top_k]
        
        return [(int(i), float(similarities[i])) for i in sorted_indices]
