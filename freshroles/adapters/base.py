"""Base adapter interface and common types."""

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel

from freshroles.models.company import CompanyConfig
from freshroles.models.enums import AdapterErrorType, ATSType
from freshroles.models.job import JobPosting, JobPostingDetail


class AdapterStatus(BaseModel):
    """Health check status for an adapter."""
    
    healthy: bool
    message: str
    last_check: datetime
    ats_type: ATSType


class AdapterError(Exception):
    """Base exception for adapter errors."""
    
    def __init__(
        self,
        message: str,
        error_type: AdapterErrorType = AdapterErrorType.UNKNOWN,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.details = details or {}


class BaseAdapter(ABC):
    """Abstract base class for ATS adapters."""
    
    ats_type: ATSType
    
    @abstractmethod
    async def discover(self, config: CompanyConfig) -> list[JobPosting]:
        """
        Discover job postings from a company's career page.
        
        Args:
            config: Company configuration with URLs and filters.
            
        Returns:
            List of normalized job postings.
            
        Raises:
            AdapterError: If discovery fails.
        """
        ...
    
    @abstractmethod
    async def fetch_detail(self, job: JobPosting) -> JobPostingDetail | None:
        """
        Fetch additional details for a job posting.
        
        Args:
            job: The job posting to fetch details for.
            
        Returns:
            Extended job posting with details, or None if not available.
        """
        ...
    
    @abstractmethod
    async def healthcheck(self) -> AdapterStatus:
        """
        Check if the adapter is healthy and the ATS is accessible.
        
        Returns:
            Status indicating health and any issues.
        """
        ...
    
    def supports_url(self, url: str) -> bool:
        """Check if this adapter can handle the given URL."""
        return False
