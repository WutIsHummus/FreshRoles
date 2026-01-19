"""Time-based filtering utilities for job postings."""

import re
from datetime import datetime, timedelta, timezone
from typing import Callable

from freshroles.models.job import JobPosting


def parse_time_filter(time_str: str) -> timedelta:
    """
    Parse a human-readable time filter string.
    
    Supports:
        - "1h", "24h" - hours
        - "1d", "7d", "30d" - days
        - "1w", "2w" - weeks
        - "1m", "3m" - months
        
    Returns:
        timedelta representing the time period.
    """
    time_str = time_str.strip().lower()
    
    match = re.match(r"^(\d+)([hdwm])$", time_str)
    if not match:
        raise ValueError(f"Invalid time filter: {time_str}. Use format like '24h', '7d', '2w', '1m'")
    
    value = int(match.group(1))
    unit = match.group(2)
    
    if unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)
    elif unit == "w":
        return timedelta(weeks=value)
    elif unit == "m":
        return timedelta(days=value * 30)  # Approximate month
    else:
        raise ValueError(f"Unknown time unit: {unit}")


def get_cutoff_time(time_filter: str) -> datetime:
    """
    Get the cutoff datetime for filtering jobs.
    
    Args:
        time_filter: Time filter string like "24h", "7d".
        
    Returns:
        datetime before which jobs should be filtered out.
    """
    delta = parse_time_filter(time_filter)
    return datetime.now(timezone.utc) - delta


def filter_jobs_by_time(
    jobs: list[JobPosting],
    time_filter: str,
) -> list[JobPosting]:
    """
    Filter jobs to only include those posted after the cutoff.
    
    Args:
        jobs: List of job postings.
        time_filter: Time filter string like "24h", "7d".
        
    Returns:
        Filtered list of jobs.
    """
    cutoff = get_cutoff_time(time_filter)
    
    filtered = []
    for job in jobs:
        if job.posted_at is None:
            # Include jobs without a date (can't verify)
            filtered.append(job)
        else:
            # Ensure timezone aware
            posted = job.posted_at
            if posted.tzinfo is None:
                posted = posted.replace(tzinfo=timezone.utc)
            
            if posted >= cutoff:
                filtered.append(job)
    
    return filtered


def get_freshness_label(posted_at: datetime | None) -> str:
    """
    Get a human-readable freshness label for a job.
    
    Returns:
        Label like "🔥 New", "📅 This week", "📆 Older".
    """
    if posted_at is None:
        return "❓ Unknown"
    
    now = datetime.now(timezone.utc)
    posted = posted_at
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    
    age = now - posted
    
    if age < timedelta(hours=24):
        return "🔥 New (today)"
    elif age < timedelta(days=3):
        return "✨ Fresh (< 3 days)"
    elif age < timedelta(days=7):
        return "📅 This week"
    elif age < timedelta(days=30):
        return "📆 This month"
    else:
        return "📦 Older"


def get_freshness_score(posted_at: datetime | None, max_age_days: int = 30) -> float:
    """
    Get a freshness score from 0.0 (old) to 1.0 (new).
    
    Used to boost recent jobs in scoring.
    """
    if posted_at is None:
        return 0.5  # Neutral
    
    now = datetime.now(timezone.utc)
    posted = posted_at
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    
    age = now - posted
    age_days = age.total_seconds() / 86400
    
    if age_days <= 0:
        return 1.0
    if age_days >= max_age_days:
        return 0.0
    
    # Exponential decay - newer jobs score much higher
    return 1.0 - (age_days / max_age_days) ** 0.5
