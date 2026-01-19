"""Ashby ATS adapter - popular with startups."""

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from freshroles.adapters.base import AdapterError, AdapterStatus, BaseAdapter
from freshroles.adapters.registry import AdapterRegistry
from freshroles.http.client import HTTPClient
from freshroles.models.company import CompanyConfig
from freshroles.models.enums import (
    AdapterErrorType,
    ATSType,
    EmploymentType,
    RemoteType,
)
from freshroles.models.job import JobPosting, JobPostingDetail


@AdapterRegistry.register(ATSType.ASHBY)
class AshbyAdapter(BaseAdapter):
    """
    Adapter for Ashby ATS.
    
    Used by: Linear, Vercel, Notion (some), Ramp, Mercury, Plaid
    URL pattern: jobs.ashbyhq.com/company
    """
    
    API_BASE = "https://jobs.ashbyhq.com/api"
    
    def __init__(self, http_client: HTTPClient | None = None):
        self._http = http_client
    
    async def _get_http(self) -> HTTPClient:
        if self._http is None:
            self._http = HTTPClient()
            await self._http.__aenter__()
        return self._http
    
    def supports_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return "ashbyhq.com" in parsed.netloc.lower()
    
    def _extract_company_slug(self, url: str) -> str | None:
        """Extract company slug from Ashby URL."""
        patterns = [
            r"jobs\.ashbyhq\.com/([^/\?]+)",
            r"ashbyhq\.com/([^/\?]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url, re.I)
            if match:
                return match.group(1)
        return None
    
    async def discover(self, config: CompanyConfig) -> list[JobPosting]:
        """Discover jobs from Ashby API."""
        jobs = []
        http = await self._get_http()
        
        for url in config.career_urls:
            company_slug = self._extract_company_slug(str(url))
            if not company_slug:
                continue
            
            # Ashby uses a posting API endpoint
            api_url = f"{self.API_BASE}/non-user-graphql?op=ApiJobBoardWithTeams"
            
            try:
                # GraphQL query to get all jobs
                payload = {
                    "operationName": "ApiJobBoardWithTeams",
                    "variables": {
                        "organizationHostedJobsPageName": company_slug
                    },
                    "query": """
                        query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
                            jobBoard: jobBoardWithTeams(
                                organizationHostedJobsPageName: $organizationHostedJobsPageName
                            ) {
                                teams {
                                    id
                                    name
                                    jobs {
                                        id
                                        title
                                        locationName
                                        employmentType
                                        publishedDate
                                        isRemote
                                    }
                                }
                            }
                        }
                    """
                }
                
                response = await http.post_json(api_url, payload)
                
                job_board = response.get("data", {}).get("jobBoard", {})
                teams = job_board.get("teams", [])
                
                for team in teams:
                    team_name = team.get("name", "")
                    raw_jobs = team.get("jobs", [])
                    
                    for raw in raw_jobs:
                        job = self._parse_job(raw, config.name, company_slug, team_name)
                        if job and self._matches_filters(job, config):
                            jobs.append(job)
                            
            except AdapterError:
                raise
            except Exception as e:
                raise AdapterError(
                    f"Failed to parse Ashby response: {e}",
                    error_type=AdapterErrorType.PARSE_ERROR,
                    details={"url": api_url, "error": str(e)},
                )
        
        return jobs
    
    def _parse_job(
        self,
        raw: dict,
        company: str,
        company_slug: str,
        department: str,
    ) -> JobPosting | None:
        """Parse a raw Ashby job into normalized format."""
        try:
            job_id = str(raw.get("id", ""))
            if not job_id:
                return None
            
            title = raw.get("title", "")
            location = raw.get("locationName", "")
            is_remote = raw.get("isRemote", False)
            
            # Parse posted date
            posted_at = None
            if published := raw.get("publishedDate"):
                try:
                    posted_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except ValueError:
                    pass
            
            # Detect remote type
            remote_type = RemoteType.REMOTE if is_remote else RemoteType.UNKNOWN
            if "hybrid" in (location or "").lower():
                remote_type = RemoteType.HYBRID
            
            # Detect employment type
            emp_type = raw.get("employmentType", "")
            employment_type = self._detect_employment_type(title, emp_type)
            
            apply_url = f"https://jobs.ashbyhq.com/{company_slug}/{job_id}"
            source_url = f"https://jobs.ashbyhq.com/{company_slug}"
            
            return JobPosting(
                company=company,
                title=title,
                source_job_id=job_id,
                source_system=ATSType.ASHBY,
                source_url=source_url,
                apply_url=apply_url,
                location=location,
                remote_type=remote_type,
                employment_type=employment_type,
                department=department,
                posted_at=posted_at,
                raw=raw,
            )
        except Exception:
            return None
    
    def _detect_employment_type(self, title: str, emp_type: str) -> EmploymentType:
        """Detect employment type from title and type field."""
        text = f"{title} {emp_type}".lower()
        
        if "intern" in text:
            return EmploymentType.INTERNSHIP
        if "contract" in text or "contractor" in text:
            return EmploymentType.CONTRACT
        if "part-time" in text or "part time" in text:
            return EmploymentType.PART_TIME
        return EmploymentType.FULL_TIME
    
    def _matches_filters(self, job: JobPosting, config: CompanyConfig) -> bool:
        """Check if job matches company filters."""
        text = f"{job.title} {job.location or ''}".lower()
        
        if config.deny_filters:
            for deny in config.deny_filters:
                if deny.lower() in text:
                    return False
        
        if config.keyword_filters:
            for keyword in config.keyword_filters:
                if keyword.lower() in text:
                    return True
            return False
        
        return True
    
    async def fetch_detail(self, job: JobPosting) -> JobPostingDetail | None:
        """Fetch detailed job info from Ashby."""
        # Ashby requires another GraphQL call for details
        return None
    
    async def healthcheck(self) -> AdapterStatus:
        """Check Ashby API health."""
        try:
            http = await self._get_http()
            await http.get("https://jobs.ashbyhq.com")
            return AdapterStatus(
                healthy=True,
                message="Ashby accessible",
                last_check=datetime.now(),
                ats_type=ATSType.ASHBY,
            )
        except Exception as e:
            return AdapterStatus(
                healthy=False,
                message=f"Ashby error: {e}",
                last_check=datetime.now(),
                ats_type=ATSType.ASHBY,
            )
