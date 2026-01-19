"""Vector-based job matching using embeddings."""

from dataclasses import dataclass

from freshroles.matching.embeddings import EmbeddingProvider, NoEmbeddingProvider
from freshroles.models.company import MatchingProfile
from freshroles.models.job import JobPosting


@dataclass
class VectorMatchResult:
    """Result from vector matching."""
    
    job: JobPosting
    similarity: float
    rank: int
    profile_highlights: list[str]


class VectorMatcher:
    """
    Match jobs to user profile using vector embeddings.
    
    Uses semantic similarity to find jobs that match the user's
    desired roles, skills, and preferences even when exact keywords
    don't match.
    """
    
    def __init__(
        self,
        profile: MatchingProfile,
        embedding_provider: EmbeddingProvider,
    ):
        """
        Initialize vector matcher.
        
        Args:
            profile: User's matching profile.
            embedding_provider: Provider for generating embeddings.
        """
        self.profile = profile
        self.provider = embedding_provider
        self._profile_embedding: list[float] | None = None
        self._profile_text: str | None = None
    
    def _build_profile_text(self) -> str:
        """Build searchable text from profile."""
        parts = []
        
        # Add desired roles
        if self.profile.desired_roles:
            parts.append("Looking for roles like: " + ", ".join(self.profile.desired_roles))
        
        # Add must-have keywords as skills
        if self.profile.must_have_keywords:
            parts.append("Required skills: " + ", ".join(self.profile.must_have_keywords))
        
        # Add location preferences
        if self.profile.preferred_locations:
            parts.append("Preferred locations: " + ", ".join(self.profile.preferred_locations))
        
        # Add remote preference
        if self.profile.remote_preference:
            parts.append(f"Work style: {self.profile.remote_preference.value}")
        
        return " ".join(parts)
    
    async def _get_profile_embedding(self) -> list[float]:
        """Get or compute profile embedding."""
        if self._profile_embedding is None:
            self._profile_text = self._build_profile_text()
            embeddings = await self.provider.embed([self._profile_text])
            self._profile_embedding = embeddings[0] if embeddings else []
        return self._profile_embedding
    
    def _build_job_text(self, job: JobPosting) -> str:
        """Build searchable text from job posting."""
        parts = [job.title]
        
        if job.department:
            parts.append(f"Department: {job.department}")
        
        if job.location:
            parts.append(f"Location: {job.location}")
        
        if job.remote_type:
            parts.append(f"Work style: {job.remote_type.value}")
        
        if job.description_text:
            # Truncate to avoid very long texts
            desc = job.description_text[:2000]
            parts.append(desc)
        
        if job.requirements:
            parts.append("Requirements: " + ", ".join(job.requirements[:10]))
        
        return " ".join(parts)
    
    async def compute_similarity(self, job: JobPosting) -> float:
        """
        Compute semantic similarity between job and profile.
        
        Returns:
            Similarity score from 0.0 to 1.0.
        """
        if isinstance(self.provider, NoEmbeddingProvider):
            return 0.5  # Neutral score when no embeddings
        
        profile_emb = await self._get_profile_embedding()
        if not profile_emb:
            return 0.5
        
        job_text = self._build_job_text(job)
        job_embeddings = await self.provider.embed([job_text])
        
        if not job_embeddings:
            return 0.5
        
        # Compute cosine similarity
        raw_sim = self.provider.similarity(profile_emb, job_embeddings[0])
        
        # Convert from [-1, 1] to [0, 1] range
        return (raw_sim + 1) / 2
    
    async def match_jobs(
        self,
        jobs: list[JobPosting],
        min_similarity: float = 0.5,
    ) -> list[VectorMatchResult]:
        """
        Match multiple jobs against the profile.
        
        Args:
            jobs: List of job postings to match.
            min_similarity: Minimum similarity threshold.
            
        Returns:
            List of match results sorted by similarity.
        """
        if isinstance(self.provider, NoEmbeddingProvider):
            # Return all jobs with neutral score when no embeddings
            return [
                VectorMatchResult(
                    job=job,
                    similarity=0.5,
                    rank=i + 1,
                    profile_highlights=["Embeddings not available"],
                )
                for i, job in enumerate(jobs)
            ]
        
        # Get profile embedding once
        profile_emb = await self._get_profile_embedding()
        if not profile_emb:
            return []
        
        # Build all job texts
        job_texts = [self._build_job_text(job) for job in jobs]
        
        # Embed all jobs at once (more efficient)
        job_embeddings = await self.provider.embed(job_texts)
        
        # Compute similarities
        results = []
        for i, job in enumerate(jobs):
            if i < len(job_embeddings):
                sim = self.provider.similarity(profile_emb, job_embeddings[i])
                # Convert to [0, 1] range
                sim = (sim + 1) / 2
                
                if sim >= min_similarity:
                    highlights = self._extract_highlights(job)
                    results.append(VectorMatchResult(
                        job=job,
                        similarity=sim,
                        rank=0,  # Will be set after sorting
                        profile_highlights=highlights,
                    ))
        
        # Sort by similarity
        results.sort(key=lambda x: x.similarity, reverse=True)
        
        # Assign ranks
        for i, result in enumerate(results):
            result.rank = i + 1
        
        return results
    
    def _extract_highlights(self, job: JobPosting) -> list[str]:
        """Extract matching highlights between job and profile."""
        highlights = []
        job_text = f"{job.title} {job.description_text or ''} {job.location or ''}".lower()
        
        # Check for matching keywords
        for keyword in self.profile.must_have_keywords:
            if keyword.lower() in job_text:
                highlights.append(f"Contains: {keyword}")
        
        # Check for matching role
        for role in self.profile.desired_roles:
            if role.lower() in job.title.lower():
                highlights.append(f"Role match: {role}")
                break
        
        # Check location match
        if job.location:
            for loc in self.profile.preferred_locations:
                if loc.lower() in job.location.lower():
                    highlights.append(f"Location: {loc}")
                    break
        
        # Check remote preference
        if self.profile.remote_preference == job.remote_type:
            highlights.append(f"Remote: {job.remote_type.value}")
        
        return highlights[:5]  # Limit highlights
