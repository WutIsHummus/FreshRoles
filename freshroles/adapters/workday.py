"""Workday ATS adapter."""

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs

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


@AdapterRegistry.register(ATSType.WORKDAY)
class WorkdayAdapter(BaseAdapter):
    """
    Adapter for Workday ATS.
    
    Workday has varied implementations. This adapter handles:
    - myworkdayjobs.com sites
    - External job search APIs
    """
    
    def __init__(self, http_client: HTTPClient | None = None):
        self._http = http_client
    
    async def _get_http(self) -> HTTPClient:
        if self._http is None:
            self._http = HTTPClient()
            await self._http.__aenter__()
        return self._http
    
    def supports_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return any(
            pattern in parsed.netloc.lower()
            for pattern in ["myworkdayjobs.com", "myworkday.com", "workday.com"]
        )
    
    def _extract_workday_info(self, url: str) -> tuple[str | None, str | None]:
        """
        Extract company and tenant info from Workday URL.
        
        Returns:
            Tuple of (company_name, api_base_url)
        """
        parsed = urlparse(url)
        
        # Pattern: company.wd5.myworkdayjobs.com
        match = re.match(r"([^.]+)\.wd(\d+)\.myworkdayjobs\.com", parsed.netloc, re.I)
        if match:
            company = match.group(1)
            wd_num = match.group(2)
            api_base = f"https://{company}.wd{wd_num}.myworkdayjobs.com/wday/cxs/{company}"
            return company, api_base
        
        # Pattern: wd5-company.myworkday.com
        match = re.match(r"wd(\d+)-([^.]+)\.myworkday\.com", parsed.netloc, re.I)
        if match:
            company = match.group(2)
            return company, None
        
        return None, None
    
    def _extract_career_site_path(self, url: str) -> str | None:
        """Extract career site path from URL."""
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")
        
        if path_parts:
            return path_parts[0]
        return None
    
    async def discover(self, config: CompanyConfig) -> list[JobPosting]:
        """Discover jobs from Workday career site."""
        jobs = []
        http = await self._get_http()
        
        for url in config.career_urls:
            url_str = str(url)
            company, api_base = self._extract_workday_info(url_str)
            
            if not company:
                continue
            
            career_site = self._extract_career_site_path(url_str) or "External"
            
            if api_base:
                try:
                    new_jobs = await self._fetch_from_api(
                        http, api_base, career_site, config
                    )
                    jobs.extend(new_jobs)
                except AdapterError:
                    raise
                except Exception as e:
                    raise AdapterError(
                        f"Failed to fetch Workday jobs: {e}",
                        error_type=AdapterErrorType.PARSE_ERROR,
                        details={"url": url_str, "error": str(e)},
                    )
        
        return jobs
    
    async def _fetch_from_api(
        self,
        http: HTTPClient,
        api_base: str,
        career_site: str,
        config: CompanyConfig,
    ) -> list[JobPosting]:
        """Fetch jobs from Workday external search API."""
        jobs = []
        offset = 0
        limit = 20
        
        while True:
            search_url = f"{api_base}/{career_site}/jobs"
            
            payload = {
                "appliedFacets": {},
                "limit": limit,
                "offset": offset,
                "searchText": "",
            }
            
            try:
                response = await http._client.post(
                    search_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
                
                job_postings = data.get("jobPostings", [])
                if not job_postings:
                    break
                
                for raw in job_postings:
                    job = self._parse_job(raw, config.name, api_base, career_site)
                    if job and self._matches_filters(job, config):
                        jobs.append(job)
                
                total = data.get("total", 0)
                offset += limit
                
                if offset >= total or offset >= 500:
                    break
                    
            except Exception as e:
                if offset == 0:
                    raise
                break
        
        return jobs
    
    def _parse_job(
        self,
        raw: dict,
        company: str,
        api_base: str,
        career_site: str,
    ) -> JobPosting | None:
        """Parse a raw Workday job into normalized format."""
        try:
            external_path = raw.get("externalPath", "")
            job_id = external_path.split("/")[-1] if external_path else ""
            
            if not job_id:
                return None
            
            title = raw.get("title", "")
            
            location_parts = []
            if loc := raw.get("locationsText"):
                location_parts.append(loc)
            location = ", ".join(location_parts) if location_parts else None
            
            posted_at = None
            if posted_on := raw.get("postedOn"):
                try:
                    posted_at = datetime.fromisoformat(
                        posted_on.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass
            
            bullet_fields = raw.get("bulletFields", [])
            
            apply_url = f"{api_base.replace('/wday/cxs/', '/')}/{career_site}{external_path}"
            source_url = f"{api_base.replace('/wday/cxs/', '/')}/{career_site}"
            
            return JobPosting(
                company=company,
                title=title,
                source_job_id=job_id,
                source_system=ATSType.WORKDAY,
                source_url=source_url,
                apply_url=apply_url,
                location=location,
                remote_type=self._detect_remote_type(title, location, bullet_fields),
                employment_type=self._detect_employment_type(title, bullet_fields),
                posted_at=posted_at,
                raw=raw,
            )
        except Exception:
            return None
    
    def _detect_remote_type(
        self,
        title: str,
        location: str | None,
        bullet_fields: list,
    ) -> RemoteType:
        """Detect remote type from job data."""
        text = f"{title} {location or ''} {' '.join(bullet_fields)}".lower()
        
        if "remote" in text:
            if "hybrid" in text:
                return RemoteType.HYBRID
            return RemoteType.REMOTE
        if "on-site" in text or "onsite" in text:
            return RemoteType.ONSITE
        return RemoteType.UNKNOWN
    
    def _detect_employment_type(
        self,
        title: str,
        bullet_fields: list,
    ) -> EmploymentType:
        """Detect employment type from title and bullet fields."""
        text = f"{title} {' '.join(bullet_fields)}".lower()
        
        if "intern" in text:
            return EmploymentType.INTERNSHIP
        if "contract" in text or "temporary" in text:
            return EmploymentType.CONTRACT
        if "part-time" in text or "part time" in text:
            return EmploymentType.PART_TIME
        if "full-time" in text or "full time" in text:
            return EmploymentType.FULL_TIME
        return EmploymentType.UNKNOWN
    
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
        """Fetch detailed job info from Workday."""
        # Workday detail fetching requires the full job path
        # This is a simplified implementation
        return None
    
    async def healthcheck(self) -> AdapterStatus:
        """Check Workday connectivity."""
        return AdapterStatus(
            healthy=True,
            message="Workday adapter ready (per-company validation needed)",
            last_check=datetime.now(),
            ats_type=ATSType.WORKDAY,
        )
