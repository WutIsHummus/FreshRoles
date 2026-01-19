"""Company and matching profile configuration models."""

from pydantic import BaseModel, Field, HttpUrl

from freshroles.models.enums import ATSType, RemoteType


class CompanyConfig(BaseModel):
    """Configuration for a company's career page."""
    
    name: str
    career_urls: list[HttpUrl]
    ats_type: ATSType | None = None
    
    country: str | None = None
    locale: str | None = None
    
    allowed_locations: list[str] = Field(default_factory=list)
    keyword_filters: list[str] = Field(default_factory=list)
    deny_filters: list[str] = Field(default_factory=list)
    
    allow_html_fallback: bool = True
    max_rps: float = Field(default=1.0, description="Max requests per second")
    
    enabled: bool = True


class MatchingProfile(BaseModel):
    """User's job matching preferences."""
    
    name: str = "default"
    
    desired_roles: list[str] = Field(
        default_factory=list,
        description="Target job titles, e.g. 'Software Engineer Intern'"
    )
    
    must_have_keywords: list[str] = Field(
        default_factory=list,
        description="Required keywords, e.g. 'Python', 'backend'"
    )
    
    must_not_keywords: list[str] = Field(
        default_factory=list,
        description="Exclude keywords, e.g. 'senior', '10+ years'"
    )
    
    preferred_locations: list[str] = Field(
        default_factory=list,
        description="Preferred work locations"
    )
    
    remote_preference: RemoteType | None = None
    
    min_score_threshold: float = Field(
        default=0.3,
        description="Minimum score to include in results"
    )
    
    # Scoring weights
    vector_weight: float = 0.55
    keyword_weight: float = 0.30
    recency_weight: float = 0.15
