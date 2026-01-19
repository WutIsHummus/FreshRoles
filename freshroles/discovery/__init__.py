"""Job discovery module."""

from freshroles.discovery.web_search import (
    search_jobs_web,
    search_intern_jobs_usa,
    run_web_search_scan,
)

__all__ = [
    "search_jobs_web",
    "search_intern_jobs_usa",
    "run_web_search_scan",
]
