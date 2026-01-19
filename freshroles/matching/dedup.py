"""Deduplication logic for job postings."""

import re
from hashlib import md5
from typing import Callable

from freshroles.models.job import JobPosting


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def simhash(text: str, hash_bits: int = 64) -> int:
    """
    Compute simhash of text for similarity detection.
    
    Simhash creates a fingerprint where similar texts have similar hashes.
    """
    words = normalize_text(text).split()
    
    if not words:
        return 0
    
    v = [0] * hash_bits
    
    for word in words:
        word_hash = int(md5(word.encode()).hexdigest(), 16)
        
        for i in range(hash_bits):
            if word_hash & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1
    
    fingerprint = 0
    for i in range(hash_bits):
        if v[i] > 0:
            fingerprint |= (1 << i)
    
    return fingerprint


def hamming_distance(hash1: int, hash2: int, bits: int = 64) -> int:
    """Compute Hamming distance between two hashes."""
    xor = hash1 ^ hash2
    return bin(xor).count("1")


def simhash_similarity(hash1: int, hash2: int, bits: int = 64) -> float:
    """
    Compute similarity based on simhash.
    
    Returns:
        Similarity from 0.0 to 1.0.
    """
    distance = hamming_distance(hash1, hash2, bits)
    return 1.0 - (distance / bits)


class Deduplicator:
    """Deduplicate job postings."""
    
    def __init__(
        self,
        similarity_threshold: float = 0.85,
        job_exists_fn: Callable[[str], bool] | None = None,
    ):
        """
        Initialize deduplicator.
        
        Args:
            similarity_threshold: Minimum simhash similarity to consider duplicate.
            job_exists_fn: Function to check if job ID exists in database.
        """
        self.similarity_threshold = similarity_threshold
        self.job_exists_fn = job_exists_fn
        self._seen_ids: set[str] = set()
        self._seen_hashes: dict[str, int] = {}
    
    def _get_exact_key(self, job: JobPosting) -> str:
        """Get exact dedup key: company + source_system + job_id."""
        return f"{job.company}:{job.source_system.value}:{job.source_job_id}"
    
    def _get_fuzzy_key(self, job: JobPosting) -> str:
        """Get fuzzy dedup key: normalized title + location."""
        title = normalize_text(job.title)
        location = normalize_text(job.location or "")
        return f"{title}:{location}"
    
    def _get_content_hash(self, job: JobPosting) -> int:
        """Get simhash of job content."""
        text = job.get_searchable_text()
        return simhash(text)
    
    def is_duplicate(self, job: JobPosting) -> bool:
        """
        Check if a job is a duplicate.
        
        Checks:
        1. Exact match: same company + source + job_id
        2. Database check: job.id already in database
        3. Fuzzy match: similar title + location + content
        """
        # Check exact key
        exact_key = self._get_exact_key(job)
        if exact_key in self._seen_ids:
            return True
        
        # Check database if function provided
        if self.job_exists_fn and self.job_exists_fn(job.id):
            return True
        
        # Check fuzzy similarity
        fuzzy_key = self._get_fuzzy_key(job)
        content_hash = self._get_content_hash(job)
        
        for seen_key, seen_hash in self._seen_hashes.items():
            # Same fuzzy key = potential duplicate
            if seen_key == fuzzy_key:
                similarity = simhash_similarity(content_hash, seen_hash)
                if similarity >= self.similarity_threshold:
                    return True
        
        # Not a duplicate, add to seen
        self._seen_ids.add(exact_key)
        self._seen_hashes[fuzzy_key] = content_hash
        
        return False
    
    def dedupe(self, jobs: list[JobPosting]) -> list[JobPosting]:
        """
        Deduplicate a list of job postings.
        
        Returns:
            List of unique jobs.
        """
        unique = []
        for job in jobs:
            if not self.is_duplicate(job):
                unique.append(job)
        return unique
    
    def reset(self):
        """Clear seen jobs cache."""
        self._seen_ids.clear()
        self._seen_hashes.clear()
