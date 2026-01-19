"""Greenhouse ATS adapter."""

import re
from datetime import datetime
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


@AdapterRegistry.register(ATSType.GREENHOUSE)
class GreenhouseAdapter(BaseAdapter):
    """Adapter for Greenhouse ATS (boards.greenhouse.io)."""
    
    API_BASE = "https://boards-api.greenhouse.io/v1/boards"
    
    def __init__(self, http_client: HTTPClient | None = None):
        self._http = http_client
    
    async def _get_http(self) -> HTTPClient:
        if self._http is None:
            self._http = HTTPClient()
            await self._http.__aenter__()
        return self._http
    
    def supports_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return "greenhouse.io" in parsed.netloc.lower()
    
    def _extract_board_token(self, url: str) -> str | None:
        """Extract board token from Greenhouse URL."""
        patterns = [
            r"boards\.greenhouse\.io/([^/\?]+)",
            r"job-boards\.greenhouse\.io/([^/\?]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url, re.I)
            if match:
                return match.group(1)
        return None
    
    async def discover(self, config: CompanyConfig) -> list[JobPosting]:
        """Discover jobs from Greenhouse board API."""
        jobs = []
        http = await self._get_http()
        
        for url in config.career_urls:
            board_token = self._extract_board_token(str(url))
            if not board_token:
                continue
            
            api_url = f"{self.API_BASE}/{board_token}/jobs"
            
            try:
                response = await http.get_json(api_url)
                raw_jobs = response.get("jobs", [])
                
                for raw in raw_jobs:
                    job = self._parse_job(raw, config.name, board_token)
                    if job and self._matches_filters(job, config):
                        jobs.append(job)
                        
            except AdapterError:
                raise
            except Exception as e:
                raise AdapterError(
                    f"Failed to parse Greenhouse response: {e}",
                    error_type=AdapterErrorType.PARSE_ERROR,
                    details={"url": api_url, "error": str(e)},
                )
        
        return jobs
    
    def _parse_job(
        self,
        raw: dict,
        company: str,
        board_token: str,
    ) -> JobPosting | None:
        """Parse a raw Greenhouse job into normalized format."""
        try:
            job_id = str(raw.get("id", ""))
            if not job_id:
                return None
            
            title = raw.get("title", "")
            location = self._extract_location(raw)
            
            posted_at = None
            if updated_at_str := raw.get("updated_at"):
                try:
                    posted_at = datetime.fromisoformat(
                        updated_at_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass
            
            apply_url = raw.get("absolute_url", "")
            source_url = f"https://boards.greenhouse.io/{board_token}"
            
            return JobPosting(
                company=company,
                title=title,
                source_job_id=job_id,
                source_system=ATSType.GREENHOUSE,
                source_url=source_url,
                apply_url=apply_url or source_url,
                location=location,
                remote_type=self._detect_remote_type(title, location),
                employment_type=self._detect_employment_type(title),
                department=self._extract_department(raw),
                posted_at=posted_at,
                raw=raw,
            )
        except Exception:
            return None
    
    def _extract_location(self, raw: dict) -> str | None:
        """Extract location from Greenhouse job data."""
        location = raw.get("location", {})
        if isinstance(location, dict):
            return location.get("name")
        return str(location) if location else None
    
    def _extract_department(self, raw: dict) -> str | None:
        """Extract department from Greenhouse job data."""
        departments = raw.get("departments", [])
        if departments and isinstance(departments, list):
            return departments[0].get("name") if departments[0] else None
        return None
    
    def _detect_remote_type(self, title: str, location: str | None) -> RemoteType:
        """Detect remote type from title and location."""
        text = f"{title} {location or ''}".lower()
        if "remote" in text:
            if "hybrid" in text:
                return RemoteType.HYBRID
            return RemoteType.REMOTE
        if "on-site" in text or "onsite" in text:
            return RemoteType.ONSITE
        return RemoteType.UNKNOWN
    
    def _detect_employment_type(self, title: str) -> EmploymentType:
        """Detect employment type from title."""
        title_lower = title.lower()
        if "intern" in title_lower:
            return EmploymentType.INTERNSHIP
        if "contract" in title_lower:
            return EmploymentType.CONTRACT
        if "part-time" in title_lower or "part time" in title_lower:
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
        """Fetch detailed job info from Greenhouse."""
        http = await self._get_http()
        
        board_token = self._extract_board_token(str(job.source_url))
        if not board_token:
            return None
        
        api_url = f"{self.API_BASE}/{board_token}/jobs/{job.source_job_id}"
        
        try:
            raw = await http.get_json(api_url)
            
            description_html = raw.get("content", "")
            description_text = self._strip_html(description_html)
            
            return JobPostingDetail(
                **job.model_dump(),
                description_html=description_html,
                description_text=description_text,
            )
        except Exception:
            return None
    
    def _strip_html(self, html: str) -> str:
        """Strip HTML tags from content."""
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()
    
    async def healthcheck(self) -> AdapterStatus:
        """Check Greenhouse API health."""
        try:
            http = await self._get_http()
            await http.get("https://boards-api.greenhouse.io/v1/boards")
            return AdapterStatus(
                healthy=True,
                message="Greenhouse API accessible",
                last_check=datetime.now(),
                ats_type=ATSType.GREENHOUSE,
            )
        except Exception as e:
            return AdapterStatus(
                healthy=False,
                message=f"Greenhouse API error: {e}",
                last_check=datetime.now(),
                ats_type=ATSType.GREENHOUSE,
            )
