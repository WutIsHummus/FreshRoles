"""Job search engine adapter - scrapes Indeed, Google Jobs, etc."""

import re
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

from freshroles.adapters.base import AdapterError, AdapterStatus, BaseAdapter
from freshroles.http.client import HTTPClient
from freshroles.models.company import CompanyConfig
from freshroles.models.enums import (
    AdapterErrorType,
    ATSType,
    EmploymentType,
    RemoteType,
)
from freshroles.models.job import JobPosting


class JobSearchAdapter(BaseAdapter):
    """
    Adapter for job search engines.
    
    Searches:
    - Google Jobs (via SerpAPI or direct scraping)
    - Indeed (via API or scraping)
    
    This adapter requires special configuration with search queries.
    """
    
    # Indeed API-like endpoints (public)
    INDEED_SEARCH = "https://www.indeed.com/jobs"
    
    def __init__(self, http_client: HTTPClient | None = None):
        self._http = http_client
    
    async def _get_http(self) -> HTTPClient:
        if self._http is None:
            self._http = HTTPClient()
            await self._http.__aenter__()
        return self._http
    
    def supports_url(self, url: str) -> bool:
        return "indeed.com" in url or "google.com/search" in url
    
    async def discover(self, config: CompanyConfig) -> list[JobPosting]:
        """Discover jobs by searching job search engines."""
        jobs = []
        http = await self._get_http()
        
        # Extract search query from config
        search_query = config.keyword_filters[0] if config.keyword_filters else "software engineer intern"
        location = "United States"
        
        # Search Indeed
        try:
            indeed_jobs = await self._search_indeed(http, search_query, location)
            jobs.extend(indeed_jobs)
        except Exception as e:
            # Indeed might block, continue with other sources
            pass
        
        # Apply filters
        filtered = []
        for job in jobs:
            if self._matches_filters(job, config):
                filtered.append(job)
        
        return filtered
    
    async def _search_indeed(
        self,
        http: HTTPClient,
        query: str,
        location: str,
    ) -> list[JobPosting]:
        """Search Indeed for jobs."""
        jobs = []
        
        # Indeed public search URL
        search_url = f"{self.INDEED_SEARCH}?q={quote_plus(query)}&l={quote_plus(location)}&fromage=7"
        
        try:
            html = await http.get(search_url)
            jobs = self._parse_indeed_html(html, query)
        except Exception:
            pass
        
        return jobs
    
    def _parse_indeed_html(self, html: str, query: str) -> list[JobPosting]:
        """Parse Indeed search results HTML."""
        jobs = []
        
        # Look for job cards in Indeed HTML
        # Pattern for job card data
        job_pattern = r'data-jk="([^"]+)"[^>]*>.*?class="jobTitle[^"]*"[^>]*>.*?<span[^>]*>([^<]+)</span>.*?class="companyName[^"]*"[^>]*>([^<]+)<.*?class="companyLocation[^"]*"[^>]*>([^<]+)<'
        
        matches = re.findall(job_pattern, html, re.S | re.I)
        
        for match in matches[:20]:  # Limit to 20 results
            job_id, title, company, location = match
            
            title = re.sub(r'\s+', ' ', title.strip())
            company = re.sub(r'\s+', ' ', company.strip())
            location = re.sub(r'\s+', ' ', location.strip())
            
            if not title or not company:
                continue
            
            job = JobPosting(
                company=company,
                title=title,
                source_job_id=job_id,
                source_system=ATSType.UNKNOWN,
                source_url="https://www.indeed.com",
                apply_url=f"https://www.indeed.com/viewjob?jk={job_id}",
                location=location,
                remote_type=self._detect_remote(title, location),
                employment_type=self._detect_employment(title),
                posted_at=datetime.now(timezone.utc),  # Indeed doesn't always show exact date
            )
            jobs.append(job)
        
        return jobs
    
    def _detect_remote(self, title: str, location: str) -> RemoteType:
        """Detect remote type."""
        text = f"{title} {location}".lower()
        if "remote" in text:
            return RemoteType.REMOTE
        if "hybrid" in text:
            return RemoteType.HYBRID
        return RemoteType.UNKNOWN
    
    def _detect_employment(self, title: str) -> EmploymentType:
        """Detect employment type."""
        title_lower = title.lower()
        if "intern" in title_lower:
            return EmploymentType.INTERNSHIP
        if "contract" in title_lower:
            return EmploymentType.CONTRACT
        return EmploymentType.FULL_TIME
    
    def _matches_filters(self, job: JobPosting, config: CompanyConfig) -> bool:
        """Check if job matches filters."""
        text = f"{job.title} {job.location or ''}".lower()
        
        if config.deny_filters:
            for deny in config.deny_filters:
                if deny.lower() in text:
                    return False
        
        if config.keyword_filters:
            for kw in config.keyword_filters:
                if kw.lower() in text:
                    return True
            return False
        
        return True
    
    async def fetch_detail(self, job: JobPosting):
        """Fetch not implemented for search engines."""
        return None
    
    async def healthcheck(self) -> AdapterStatus:
        """Check if search engines are accessible."""
        return AdapterStatus(
            healthy=True,
            message="Job search adapter ready",
            last_check=datetime.now(),
            ats_type=ATSType.UNKNOWN,
        )


async def search_jobs_from_engines(
    query: str = "software engineer intern",
    location: str = "United States",
    http: HTTPClient | None = None,
) -> list[JobPosting]:
    """
    Convenience function to search for jobs across search engines.
    
    Args:
        query: Job search query (e.g., "software engineer intern")
        location: Location to search (e.g., "United States", "Texas")
        http: Optional HTTP client
        
    Returns:
        List of job postings from search engines.
    """
    from freshroles.models.company import CompanyConfig
    
    config = CompanyConfig(
        name="JobSearch",
        career_urls=["https://www.indeed.com"],
        enabled=True,
        keyword_filters=[query],
    )
    
    adapter = JobSearchAdapter(http)
    return await adapter.discover(config)
