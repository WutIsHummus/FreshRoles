"""Combined scoring pipeline."""

from freshroles.matching.embeddings import (
    EmbeddingProvider,
    NoEmbeddingProvider,
    OllamaEmbeddingProvider,
)
from freshroles.matching.keyword import KeywordScorer, RecencyScorer
from freshroles.models.company import MatchingProfile
from freshroles.models.job import JobPosting, ScoredJobPosting


async def get_default_embedding_provider() -> EmbeddingProvider:
    """
    Get the best available embedding provider.
    
    Priority:
    1. Ollama (if server is running)
    2. NoEmbedding fallback
    """
    # Try Ollama first
    ollama = OllamaEmbeddingProvider(model="nomic-embed-text")
    if await ollama.is_available():
        print("Using Ollama embeddings (nomic-embed-text)")
        return ollama
    
    # Fallback to no embeddings
    print("Ollama not available, using keyword-only matching")
    return NoEmbeddingProvider()


class Scorer:
    """
    Combined job scorer using multiple signals.
    
    Formula:
        final_score = vector_weight * vector_score 
                    + keyword_weight * keyword_score 
                    + recency_weight * recency_score
    """
    
    def __init__(
        self,
        profile: MatchingProfile,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.profile = profile
        self.embedding_provider = embedding_provider or NoEmbeddingProvider()
        self.keyword_scorer = KeywordScorer(profile)
        self.recency_scorer = RecencyScorer()
        
        self._profile_embedding: list[float] | None = None
    
    async def _get_profile_embedding(self) -> list[float]:
        """Get embedding for the user's profile."""
        if self._profile_embedding is None:
            profile_text = " ".join([
                *self.profile.desired_roles,
                *self.profile.must_have_keywords,
            ])
            if profile_text:
                embeddings = await self.embedding_provider.embed([profile_text])
                self._profile_embedding = embeddings[0] if embeddings else []
            else:
                self._profile_embedding = []
        return self._profile_embedding
    
    async def score(self, job: JobPosting) -> ScoredJobPosting:
        """
        Score a single job posting.
        
        Returns:
            ScoredJobPosting with all score components.
        """
        keyword_score, keyword_reasons = self.keyword_scorer.score(job)
        
        if keyword_score == 0.0 and keyword_reasons:
            return ScoredJobPosting(
                job=job,
                final_score=0.0,
                keyword_score=0.0,
                match_reasons=keyword_reasons,
            )
        
        recency_score = self.recency_scorer.score(job)
        
        vector_score = 0.5
        if not isinstance(self.embedding_provider, NoEmbeddingProvider):
            try:
                profile_emb = await self._get_profile_embedding()
                if profile_emb:
                    job_text = job.get_searchable_text()
                    job_embeddings = await self.embedding_provider.embed([job_text])
                    if job_embeddings:
                        raw_sim = self.embedding_provider.similarity(
                            profile_emb, job_embeddings[0]
                        )
                        vector_score = (raw_sim + 1) / 2
            except Exception:
                vector_score = 0.5
        
        final_score = (
            self.profile.vector_weight * vector_score
            + self.profile.keyword_weight * keyword_score
            + self.profile.recency_weight * recency_score
        )
        
        reasons = keyword_reasons.copy()
        if vector_score > 0.6:
            reasons.append(f"High semantic similarity: {vector_score:.2f}")
        if recency_score > 0.7:
            reasons.append("Recently posted")
        
        return ScoredJobPosting(
            job=job,
            final_score=final_score,
            vector_score=vector_score,
            keyword_score=keyword_score,
            recency_score=recency_score,
            match_reasons=reasons,
        )
    
    async def score_batch(
        self,
        jobs: list[JobPosting],
        min_score: float | None = None,
    ) -> list[ScoredJobPosting]:
        """
        Score a batch of job postings.
        
        Args:
            jobs: List of jobs to score.
            min_score: Minimum score threshold (uses profile default if None).
            
        Returns:
            List of scored jobs, sorted by score descending.
        """
        threshold = min_score if min_score is not None else self.profile.min_score_threshold
        
        scored = []
        for job in jobs:
            scored_job = await self.score(job)
            if scored_job.final_score >= threshold:
                scored.append(scored_job)
        
        scored.sort(key=lambda x: x.final_score, reverse=True)
        return scored
