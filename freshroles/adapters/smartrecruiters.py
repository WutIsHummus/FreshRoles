"""SmartRecruiters ATS adapter - enterprise companies."""

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


@AdapterRegistry.register(ATSType.SMARTRECRUITERS)
class SmartRecruitersAdapter(BaseAdapter):
    """
    Adapter for SmartRecruiters ATS.
    
    Used by: Visa, IKEA, LinkedIn, Sephora, Bosch
    URL pattern: jobs.smartrecruiters.com/CompanyName
    """
    
    API_BASE = "https://api.smartrecruiters.com/v1/companies"
    
    def __init__(self, http_client: HTTPClient | None = None):
        self._http = http_client
    
    async def _get_http(self) -> HTTPClient:
        if self._http is None:
            self._http = HTTPClient()
            await self._http.__aenter__()
        return self._http
    
    def supports_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return "smartrecruiters.com" in parsed.netloc.lower()
    
    def _extract_company_id(self, url: str) -> str | None:
        """Extract company ID from SmartRecruiters URL."""
        patterns = [
            r"jobs\.smartrecruiters\.com/([^/\?]+)",
            r"careers\.smartrecruiters\.com/([^/\?]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url, re.I)
            if match:
                return match.group(1)
        return None
    
    async def discover(self, config: CompanyConfig) -> list[JobPosting]:
        """Discover jobs from SmartRecruiters API."""
        jobs = []
        http = await self._get_http()
        
        for url in config.career_urls:
            company_id = self._extract_company_id(str(url))
            if not company_id:
                continue
            
            api_url = f"{self.API_BASE}/{company_id}/postings"
            offset = 0
            limit = 100
            
            try:
                while True:
                    response = await http.get_json(
                        api_url,
                        params={"offset": offset, "limit": limit}
                    )
                    
                    content = response.get("content", [])
                    if not content:
                        break
                    
                    for raw in content:
                        job = self._parse_job(raw, config.name, company_id)
                        if job and self._matches_filters(job, config):
                            jobs.append(job)
                    
                    # Check if there are more pages
                    total = response.get("totalFound", 0)
                    offset += limit
                    if offset >= total:
                        break
                        
            except AdapterError:
                raise
            except Exception as e:
                raise AdapterError(
                    f"Failed to parse SmartRecruiters response: {e}",
                    error_type=AdapterErrorType.PARSE_ERROR,
                    details={"url": api_url, "error": str(e)},
                )
        
        return jobs
    
    def _parse_job(
        self,
        raw: dict,
        company: str,
        company_id: str,
    ) -> JobPosting | None:
        """Parse a raw SmartRecruiters job into normalized format."""
        try:
            job_id = str(raw.get("id", "") or raw.get("refNumber", ""))
            if not job_id:
                return None
            
            title = raw.get("name", "")
            
            # Extract location
            location_obj = raw.get("location", {})
            location_parts = []
            if city := location_obj.get("city"):
                location_parts.append(city)
            if region := location_obj.get("region"):
                location_parts.append(region)
            if country := location_obj.get("country"):
                location_parts.append(country)
            location = ", ".join(location_parts) if location_parts else None
            
            # Extract department
            department = None
            if dept := raw.get("department"):
                department = dept.get("label", dept.get("id", ""))
            
            # Parse posted date
            posted_at = None
            if released := raw.get("releasedDate"):
                try:
                    posted_at = datetime.fromisoformat(released.replace("Z", "+00:00"))
                except ValueError:
                    pass
            
            # Detect remote type
            remote_type = RemoteType.UNKNOWN
            if raw.get("remote"):
                remote_type = RemoteType.REMOTE
            
            # Detect employment type
            employment_type = self._detect_employment_type(title, raw)
            
            apply_url = raw.get("applyUrl", f"https://jobs.smartrecruiters.com/{company_id}/{job_id}")
            source_url = f"https://jobs.smartrecruiters.com/{company_id}"
            
            return JobPosting(
                company=company,
                title=title,
                source_job_id=job_id,
                source_system=ATSType.SMARTRECRUITERS,
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
    
    def _detect_employment_type(self, title: str, raw: dict) -> EmploymentType:
        """Detect employment type from title and job data."""
        type_code = raw.get("typeOfEmployment", {}).get("id", "")
        title_lower = title.lower()
        
        if "intern" in title_lower or type_code == "intern":
            return EmploymentType.INTERNSHIP
        if "contract" in title_lower or type_code == "contractor":
            return EmploymentType.CONTRACT
        if "part" in title_lower or type_code == "part_time":
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
        """Fetch detailed job info from SmartRecruiters."""
        return None
    
    async def healthcheck(self) -> AdapterStatus:
        """Check SmartRecruiters API health."""
        try:
            http = await self._get_http()
            await http.get("https://jobs.smartrecruiters.com")
            return AdapterStatus(
                healthy=True,
                message="SmartRecruiters accessible",
                last_check=datetime.now(),
                ats_type=ATSType.SMARTRECRUITERS,
            )
        except Exception as e:
            return AdapterStatus(
                healthy=False,
                message=f"SmartRecruiters error: {e}",
                last_check=datetime.now(),
                ats_type=ATSType.SMARTRECRUITERS,
            )
