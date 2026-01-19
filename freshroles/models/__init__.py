"""FreshRoles data models."""

from freshroles.models.enums import (
    ATSType,
    AdapterErrorType,
    EmploymentType,
    RemoteType,
)
from freshroles.models.job import JobPosting, JobPostingDetail
from freshroles.models.company import CompanyConfig, MatchingProfile

__all__ = [
    "ATSType",
    "AdapterErrorType",
    "EmploymentType",
    "RemoteType",
    "JobPosting",
    "JobPostingDetail",
    "CompanyConfig",
    "MatchingProfile",
]
