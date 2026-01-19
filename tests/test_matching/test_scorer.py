"""Tests for matching functionality."""

import pytest
from datetime import datetime, timedelta, timezone

from freshroles.matching.keyword import KeywordScorer, RecencyScorer
from freshroles.matching.dedup import Deduplicator, simhash, simhash_similarity
from freshroles.matching.scorer import Scorer
from freshroles.matching.embeddings import NoEmbeddingProvider
from freshroles.models.company import MatchingProfile
from freshroles.models.job import JobPosting
from freshroles.models.enums import ATSType, RemoteType


@pytest.fixture
def sample_profile():
    """Create sample matching profile."""
    return MatchingProfile(
        name="test",
        desired_roles=["Software Engineer Intern", "Backend Intern"],
        must_have_keywords=["Python", "backend"],
        must_not_keywords=["senior", "staff"],
        preferred_locations=["San Francisco", "Remote"],
        remote_preference=RemoteType.REMOTE,
    )


@pytest.fixture
def sample_job():
    """Create sample job posting."""
    return JobPosting(
        company="TestCo",
        title="Software Engineer Intern",
        source_job_id="12345",
        source_system=ATSType.GREENHOUSE,
        source_url="https://example.com/careers",
        apply_url="https://example.com/apply/12345",
        location="San Francisco, CA (Remote)",
        remote_type=RemoteType.REMOTE,
        description_text="Looking for a Python backend developer intern.",
        posted_at=datetime.now(timezone.utc) - timedelta(days=1),
    )


class TestKeywordScorer:
    """Tests for KeywordScorer."""
    
    def test_role_match(self, sample_profile, sample_job):
        """Test role matching boosts score."""
        scorer = KeywordScorer(sample_profile)
        score, reasons = scorer.score(sample_job)
        
        assert score > 0.3
        assert any("Role match" in r for r in reasons)
    
    def test_must_not_keywords_exclude(self, sample_profile):
        """Test must-not keywords exclude jobs."""
        scorer = KeywordScorer(sample_profile)
        
        job = JobPosting(
            company="TestCo",
            title="Senior Software Engineer",
            source_job_id="12346",
            source_system=ATSType.GREENHOUSE,
            source_url="https://example.com/careers",
            apply_url="https://example.com/apply/12346",
        )
        
        score, reasons = scorer.score(job)
        assert score == 0.0
        assert any("Excluded" in r for r in reasons)
    
    def test_keyword_match(self, sample_profile, sample_job):
        """Test keyword matching."""
        scorer = KeywordScorer(sample_profile)
        score, reasons = scorer.score(sample_job)
        
        assert any("Keyword" in r for r in reasons)


class TestRecencyScorer:
    """Tests for RecencyScorer."""
    
    def test_fresh_job_high_score(self):
        """Test recently posted jobs get high scores."""
        scorer = RecencyScorer(max_age_days=30)
        
        job = JobPosting(
            company="TestCo",
            title="Engineer",
            source_job_id="123",
            source_system=ATSType.GREENHOUSE,
            source_url="https://example.com",
            apply_url="https://example.com/apply",
            posted_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        
        score = scorer.score(job)
        assert score > 0.9
    
    def test_old_job_low_score(self):
        """Test old jobs get low scores."""
        scorer = RecencyScorer(max_age_days=30)
        
        job = JobPosting(
            company="TestCo",
            title="Engineer",
            source_job_id="123",
            source_system=ATSType.GREENHOUSE,
            source_url="https://example.com",
            apply_url="https://example.com/apply",
            posted_at=datetime.now(timezone.utc) - timedelta(days=25),
        )
        
        score = scorer.score(job)
        assert score < 0.3


class TestDeduplicator:
    """Tests for Deduplicator."""
    
    def test_exact_duplicate(self):
        """Test exact duplicate detection."""
        dedup = Deduplicator()
        
        job1 = JobPosting(
            company="TestCo",
            title="Engineer",
            source_job_id="123",
            source_system=ATSType.GREENHOUSE,
            source_url="https://example.com",
            apply_url="https://example.com/apply",
        )
        
        job2 = JobPosting(
            company="TestCo",
            title="Engineer",
            source_job_id="123",
            source_system=ATSType.GREENHOUSE,
            source_url="https://example.com",
            apply_url="https://example.com/apply",
        )
        
        assert not dedup.is_duplicate(job1)
        assert dedup.is_duplicate(job2)
    
    def test_dedupe_list(self):
        """Test deduplicating a list of jobs."""
        dedup = Deduplicator()
        
        jobs = [
            JobPosting(
                company="TestCo",
                title=f"Engineer {i}",
                source_job_id=str(i),
                source_system=ATSType.GREENHOUSE,
                source_url="https://example.com",
                apply_url="https://example.com/apply",
            )
            for i in range(5)
        ]
        
        # Add a duplicate
        jobs.append(jobs[0].model_copy())
        
        unique = dedup.dedupe(jobs)
        assert len(unique) == 5


class TestSimhash:
    """Tests for simhash functions."""
    
    def test_similar_texts(self):
        """Test similar texts have similar hashes."""
        text1 = "Software Engineer position in San Francisco"
        text2 = "Software Engineer role in San Francisco Bay Area"
        
        hash1 = simhash(text1)
        hash2 = simhash(text2)
        
        similarity = simhash_similarity(hash1, hash2)
        assert similarity > 0.7
    
    def test_different_texts(self):
        """Test different texts have different hashes."""
        text1 = "Software Engineer position in San Francisco"
        text2 = "Product Manager role in New York"
        
        hash1 = simhash(text1)
        hash2 = simhash(text2)
        
        similarity = simhash_similarity(hash1, hash2)
        assert similarity < 0.7


class TestScorer:
    """Tests for combined Scorer."""
    
    @pytest.mark.asyncio
    async def test_combined_scoring(self, sample_profile, sample_job):
        """Test combined scoring with all components."""
        scorer = Scorer(sample_profile, NoEmbeddingProvider())
        
        result = await scorer.score(sample_job)
        
        assert result.final_score > 0
        assert result.keyword_score >= 0
        assert result.recency_score >= 0
        assert len(result.match_reasons) > 0
    
    @pytest.mark.asyncio
    async def test_batch_scoring(self, sample_profile):
        """Test batch scoring with threshold."""
        scorer = Scorer(sample_profile, NoEmbeddingProvider())
        
        jobs = [
            JobPosting(
                company="TestCo",
                title="Software Engineer Intern",
                source_job_id="1",
                source_system=ATSType.GREENHOUSE,
                source_url="https://example.com",
                apply_url="https://example.com/apply",
                description_text="Python backend developer position",
                posted_at=datetime.now(timezone.utc),
            ),
            JobPosting(
                company="TestCo",
                title="Senior Staff Engineer",  # Should be excluded
                source_job_id="2",
                source_system=ATSType.GREENHOUSE,
                source_url="https://example.com",
                apply_url="https://example.com/apply",
            ),
        ]
        
        results = await scorer.score_batch(jobs, min_score=0.1)
        
        # Only non-excluded job should be returned
        assert len(results) == 1
        assert results[0].job.title == "Software Engineer Intern"
