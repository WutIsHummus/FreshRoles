"""Keyword-based matching scorer."""

import re
from datetime import datetime, timedelta, timezone

from freshroles.models.company import MatchingProfile
from freshroles.models.job import JobPosting


class KeywordScorer:
    """Score jobs based on keyword matching."""
    
    def __init__(self, profile: MatchingProfile):
        self.profile = profile
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for keywords."""
        self._must_have = [
            re.compile(rf"\b{re.escape(kw)}\b", re.I)
            for kw in self.profile.must_have_keywords
        ]
        self._must_not = [
            re.compile(rf"\b{re.escape(kw)}\b", re.I)
            for kw in self.profile.must_not_keywords
        ]
        self._desired_roles = [
            re.compile(rf"\b{re.escape(role)}\b", re.I)
            for role in self.profile.desired_roles
        ]
    
    def score(self, job: JobPosting) -> tuple[float, list[str]]:
        """
        Score a job based on keyword matching.
        
        Returns:
            Tuple of (score 0.0-1.0, list of match reasons).
        """
        text = job.get_searchable_text()
        title = job.title.lower()
        reasons = []
        
        for pattern in self._must_not:
            if pattern.search(text):
                return 0.0, [f"Excluded: contains '{pattern.pattern}'"]
        
        score = 0.0
        
        role_match_score = 0.0
        for pattern in self._desired_roles:
            if pattern.search(title):
                role_match_score = 0.4
                reasons.append(f"Role match: {pattern.pattern}")
                break
        score += role_match_score
        
        if self._must_have:
            matched_count = 0
            for pattern in self._must_have:
                if pattern.search(text):
                    matched_count += 1
                    reasons.append(f"Keyword: {pattern.pattern}")
            
            keyword_score = (matched_count / len(self._must_have)) * 0.4
            score += keyword_score
        else:
            score += 0.2
        
        if job.location and self.profile.preferred_locations:
            loc_lower = job.location.lower()
            for pref_loc in self.profile.preferred_locations:
                if pref_loc.lower() in loc_lower:
                    score += 0.1
                    reasons.append(f"Location: {pref_loc}")
                    break
        
        if self.profile.remote_preference and job.remote_type == self.profile.remote_preference:
            score += 0.1
            reasons.append(f"Remote: {job.remote_type.value}")
        
        return min(score, 1.0), reasons


class RecencyScorer:
    """Score jobs based on posting recency."""
    
    def __init__(self, max_age_days: int = 30):
        self.max_age_days = max_age_days
    
    def score(self, job: JobPosting) -> float:
        """
        Score a job based on how recently it was posted.
        
        Returns:
            Score from 0.0 (old) to 1.0 (fresh).
        """
        if not job.posted_at:
            return 0.5
        
        now = datetime.now(timezone.utc)
        posted = job.posted_at
        
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        
        age = now - posted
        age_days = age.total_seconds() / 86400
        
        if age_days <= 0:
            return 1.0
        if age_days >= self.max_age_days:
            return 0.0
        
        decay = 1.0 - (age_days / self.max_age_days) ** 0.5
        return max(0.0, min(1.0, decay))
