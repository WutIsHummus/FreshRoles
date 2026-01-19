"""Lever ATS adapter."""

import re
from datetime import datetime
from urllib.parse import urlparse

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


@AdapterRegistry.register(ATSType.LEVER)
class LeverAdapter(BaseAdapter):
    """Adapter for Lever ATS (jobs.lever.co)."""
    
    API_BASE = "https://api.lever.co/v0/postings"
    
    def __init__(self, http_client: HTTPClient | None = None):
        self._http = http_client
    
    async def _get_http(self) -> HTTPClient:
        if self._http is None:
            self._http = HTTPClient()
            await self._http.__aenter__()
        return self._http
    
    def supports_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return "lever.co" in parsed.netloc.lower()
    
    def _extract_company_slug(self, url: str) -> str | None:
        """Extract company slug from Lever URL."""
        patterns = [
            r"jobs\.lever\.co/([^/\?]+)",
            r"lever\.co/([^/\?]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url, re.I)
            if match:
                return match.group(1)
        return None
    
    async def discover(self, config: CompanyConfig) -> list[JobPosting]:
        """Discover jobs from Lever postings API."""
        jobs = []
        http = await self._get_http()
        
        for url in config.career_urls:
            company_slug = self._extract_company_slug(str(url))
            if not company_slug:
                continue
            
            api_url = f"{self.API_BASE}/{company_slug}?mode=json"
            
            try:
                raw_jobs = await http.get_json(api_url)
                
                if not isinstance(raw_jobs, list):
                    raw_jobs = []
                
                for raw in raw_jobs:
                    job = self._parse_job(raw, config.name, company_slug)
                    if job and self._matches_filters(job, config):
                        jobs.append(job)
                        
            except AdapterError:
                raise
            except Exception as e:
                raise AdapterError(
                    f"Failed to parse Lever response: {e}",
                    error_type=AdapterErrorType.PARSE_ERROR,
                    details={"url": api_url, "error": str(e)},
                )
        
        return jobs
    
    def _parse_job(
        self,
        raw: dict,
        company: str,
        company_slug: str,
    ) -> JobPosting | None:
        """Parse a raw Lever job into normalized format."""
        try:
            job_id = raw.get("id", "")
            if not job_id:
                return None
            
            title = raw.get("text", "")
            
            categories = raw.get("categories", {})
            location = categories.get("location", "")
            department = categories.get("department", "")
            team = categories.get("team", "")
            commitment = categories.get("commitment", "")
            
            posted_at = None
            if created_at := raw.get("createdAt"):
                try:
                    posted_at = datetime.fromtimestamp(created_at / 1000)
                except (ValueError, TypeError):
                    pass
            
            apply_url = raw.get("applyUrl", raw.get("hostedUrl", ""))
            source_url = f"https://jobs.lever.co/{company_slug}"
            
            return JobPosting(
                company=company,
                title=title,
                source_job_id=job_id,
                source_system=ATSType.LEVER,
                source_url=source_url,
                apply_url=apply_url or source_url,
                location=location or None,
                remote_type=self._detect_remote_type(title, location, commitment),
                employment_type=self._detect_employment_type(title, commitment),
                department=department or None,
                team=team or None,
                posted_at=posted_at,
                raw=raw,
            )
        except Exception:
            return None
    
    def _detect_remote_type(
        self,
        title: str,
        location: str,
        commitment: str,
    ) -> RemoteType:
        """Detect remote type from job data."""
        text = f"{title} {location} {commitment}".lower()
        if "remote" in text:
            if "hybrid" in text:
                return RemoteType.HYBRID
            return RemoteType.REMOTE
        if "on-site" in text or "onsite" in text:
            return RemoteType.ONSITE
        return RemoteType.UNKNOWN
    
    def _detect_employment_type(self, title: str, commitment: str) -> EmploymentType:
        """Detect employment type from title and commitment."""
        text = f"{title} {commitment}".lower()
        if "intern" in text:
            return EmploymentType.INTERNSHIP
        if "contract" in text:
            return EmploymentType.CONTRACT
        if "part-time" in text or "part time" in text:
            return EmploymentType.PART_TIME
        if "full-time" in text or "full time" in text:
            return EmploymentType.FULL_TIME
        return EmploymentType.UNKNOWN
    
    def _matches_filters(self, job: JobPosting, config: CompanyConfig) -> bool:
        """Check if job matches company filters."""
        text = f"{job.title} {job.location or ''} {job.department or ''}".lower()
        
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
        """Fetch detailed job info from Lever."""
        http = await self._get_http()
        
        company_slug = self._extract_company_slug(str(job.source_url))
        if not company_slug:
            return None
        
        api_url = f"{self.API_BASE}/{company_slug}/{job.source_job_id}"
        
        try:
            raw = await http.get_json(api_url)
            
            description_html = raw.get("descriptionHtml", "")
            description_text = raw.get("descriptionPlain", "")
            
            additional = raw.get("additional", "")
            if additional:
                description_text = f"{description_text}\n\n{additional}"
            
            lists = raw.get("lists", [])
            requirements = []
            for lst in lists:
                if "requirement" in lst.get("text", "").lower():
                    requirements.extend(
                        item.get("text", "")
                        for item in lst.get("content", [])
                    )
            
            return JobPostingDetail(
                **job.model_dump(),
                description_html=description_html,
                description_text=description_text,
                requirements=requirements,
            )
        except Exception:
            return None
    
    async def healthcheck(self) -> AdapterStatus:
        """Check Lever API health."""
        try:
            http = await self._get_http()
            await http.get("https://api.lever.co/v0/postings/lever")
            return AdapterStatus(
                healthy=True,
                message="Lever API accessible",
                last_check=datetime.now(),
                ats_type=ATSType.LEVER,
            )
        except Exception as e:
            return AdapterStatus(
                healthy=False,
                message=f"Lever API error: {e}",
                last_check=datetime.now(),
                ats_type=ATSType.LEVER,
            )
