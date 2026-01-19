"""Job posting data models."""

from datetime import datetime
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, computed_field

from freshroles.models.enums import ATSType, EmploymentType, RemoteType


class JobPosting(BaseModel):
    """Normalized job posting from any ATS system."""
    
    company: str
    title: str
    source_job_id: str = Field(description="Original job ID from the ATS")
    source_system: ATSType
    source_url: HttpUrl
    apply_url: HttpUrl
    
    location: str | None = None
    remote_type: RemoteType = RemoteType.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    department: str | None = None
    team: str | None = None
    
    posted_at: datetime | None = None
    updated_at: datetime | None = None
    
    description_html: str | None = None
    description_text: str | None = None
    requirements: list[str] = Field(default_factory=list)
    seniority: str | None = None
    keywords: list[str] = Field(default_factory=list)
    
    raw: dict[str, Any] = Field(default_factory=dict, description="Original payload for debugging")
    
    @computed_field
    @property
    def id(self) -> str:
        """Stable hash ID: company + source_system + source_job_id."""
        key = f"{self.company}:{self.source_system.value}:{self.source_job_id}"
        return sha256(key.encode()).hexdigest()[:16]
    
    def get_searchable_text(self) -> str:
        """Get combined text for matching/embedding."""
        parts = [self.title]
        if self.description_text:
            parts.append(self.description_text)
        if self.requirements:
            parts.extend(self.requirements)
        if self.department:
            parts.append(self.department)
        return " ".join(parts)


class JobPostingDetail(JobPosting):
    """Extended job posting with additional details fetched separately."""
    
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    benefits: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    experience_years_min: int | None = None
    experience_years_max: int | None = None


class ScoredJobPosting(BaseModel):
    """Job posting with matching scores."""
    
    job: JobPosting
    final_score: float = 0.0
    vector_score: float = 0.0
    keyword_score: float = 0.0
    recency_score: float = 0.0
    match_reasons: list[str] = Field(default_factory=list)
