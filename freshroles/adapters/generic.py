"""Generic HTML scraper for career pages without API."""

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

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


class GenericHTMLAdapter(BaseAdapter):
    """
    Generic adapter for scraping career pages via HTML.
    
    This adapter extracts job links from any career page using
    common patterns. It's a fallback when no specific ATS adapter exists.
    
    Note: This adapter is NOT registered automatically. Use it directly
    when you need to scrape a non-standard career page.
    """
    
    # Common patterns for job listing links
    JOB_LINK_PATTERNS = [
        r'href=["\']([^"\']*(?:job|career|position|opening|apply)[^"\']*)["\']',
        r'href=["\']([^"\']+/jobs?/[^"\']+)["\']',
        r'href=["\']([^"\']+/careers?/[^"\']+)["\']',
    ]
    
    # Patterns for job titles
    TITLE_PATTERNS = [
        r'<h[123][^>]*class="[^"]*(?:job|position|title)[^"]*"[^>]*>([^<]+)</h[123]>',
        r'<a[^>]*class="[^"]*(?:job|position)[^"]*"[^>]*>([^<]+)</a>',
        r'<span[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</span>',
    ]
    
    # Pattern for dates
    DATE_PATTERNS = [
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
    ]
    
    def __init__(self, http_client: HTTPClient | None = None):
        self._http = http_client
    
    async def _get_http(self) -> HTTPClient:
        if self._http is None:
            self._http = HTTPClient()
            await self._http.__aenter__()
        return self._http
    
    def supports_url(self, url: str) -> bool:
        # Generic adapter supports any URL
        return True
    
    async def discover(self, config: CompanyConfig) -> list[JobPosting]:
        """Discover jobs by scraping HTML career pages."""
        jobs = []
        http = await self._get_http()
        
        for url in config.career_urls:
            try:
                html = await http.get(str(url))
                extracted = self._extract_jobs_from_html(html, str(url), config.name)
                
                for job in extracted:
                    if self._matches_filters(job, config):
                        jobs.append(job)
                        
            except AdapterError:
                raise
            except Exception as e:
                raise AdapterError(
                    f"Failed to scrape career page: {e}",
                    error_type=AdapterErrorType.PARSE_ERROR,
                    details={"url": str(url), "error": str(e)},
                )
        
        return jobs
    
    def _extract_jobs_from_html(
        self,
        html: str,
        source_url: str,
        company: str,
    ) -> list[JobPosting]:
        """Extract job postings from HTML content."""
        jobs = []
        seen_urls = set()
        
        # Find all potential job links
        for pattern in self.JOB_LINK_PATTERNS:
            matches = re.findall(pattern, html, re.I)
            
            for href in matches:
                # Normalize URL
                job_url = urljoin(source_url, href)
                
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)
                
                # Skip if it's not actually a job link
                if not self._is_job_url(job_url):
                    continue
                
                # Try to extract title from the surrounding context
                title = self._extract_title_for_link(html, href)
                if not title:
                    # Use URL path as fallback
                    title = self._title_from_url(job_url)
                
                if not title:
                    continue
                
                # Generate a job ID from the URL
                job_id = self._id_from_url(job_url)
                
                # Try to extract location
                location = self._extract_location_near_link(html, href)
                
                job = JobPosting(
                    company=company,
                    title=title,
                    source_job_id=job_id,
                    source_system=ATSType.UNKNOWN,
                    source_url=source_url,
                    apply_url=job_url,
                    location=location,
                    remote_type=self._detect_remote_type(title, location),
                    employment_type=self._detect_employment_type(title),
                )
                jobs.append(job)
        
        return jobs
    
    def _is_job_url(self, url: str) -> bool:
        """Check if URL appears to be a job posting."""
        # Skip common non-job URLs
        skip_patterns = [
            r'/about', r'/contact', r'/privacy', r'/terms',
            r'/benefits', r'/culture', r'/team', r'/blog',
            r'\.pdf$', r'\.jpg$', r'\.png$',
        ]
        url_lower = url.lower()
        for pattern in skip_patterns:
            if re.search(pattern, url_lower):
                return False
        return True
    
    def _extract_title_for_link(self, html: str, href: str) -> str | None:
        """Try to extract job title for a specific link."""
        # Look for the link in context
        escaped_href = re.escape(href)
        patterns = [
            rf'<a[^>]*href=["\']?{escaped_href}["\']?[^>]*>([^<]+)</a>',
            rf'>([^<]+)</a>\s*<a[^>]*href=["\']?{escaped_href}',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.I | re.S)
            if match:
                title = match.group(1).strip()
                title = re.sub(r'\s+', ' ', title)
                if len(title) > 5 and len(title) < 200:
                    return title
        return None
    
    def _title_from_url(self, url: str) -> str | None:
        """Extract a title from URL path."""
        parsed = urlparse(url)
        path = parsed.path
        
        # Get last path segment
        segments = [s for s in path.split('/') if s]
        if not segments:
            return None
        
        title = segments[-1]
        # Replace dashes/underscores with spaces
        title = re.sub(r'[-_]+', ' ', title)
        # Remove file extensions
        title = re.sub(r'\.\w+$', '', title)
        # Skip if too short or looks like an ID
        if len(title) < 5 or title.isdigit():
            return None
        
        return title.title()
    
    def _id_from_url(self, url: str) -> str:
        """Generate a unique ID from URL."""
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:12]
    
    def _extract_location_near_link(self, html: str, href: str) -> str | None:
        """Try to extract location near a job link."""
        # Look for location patterns near the link
        escaped_href = re.escape(href)
        # Find context around the link (500 chars before and after)
        match = re.search(rf'.{{0,500}}{escaped_href}.{{0,500}}', html, re.I | re.S)
        if not match:
            return None
        
        context = match.group(0)
        
        # Look for location patterns
        location_patterns = [
            r'(?:Location|City|Office):\s*([^<\n]+)',
            r'<span[^>]*class="[^"]*location[^"]*"[^>]*>([^<]+)</span>',
        ]
        
        for pattern in location_patterns:
            loc_match = re.search(pattern, context, re.I)
            if loc_match:
                return loc_match.group(1).strip()
        
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
    
    async def fetch_detail(self, job: JobPosting) -> None:
        """Fetch is not supported for generic scraper."""
        return None
    
    async def healthcheck(self) -> AdapterStatus:
        """Generic adapter is always healthy."""
        return AdapterStatus(
            healthy=True,
            message="Generic HTML scraper ready",
            last_check=datetime.now(),
            ats_type=ATSType.UNKNOWN,
        )
