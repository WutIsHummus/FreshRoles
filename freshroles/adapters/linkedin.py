"""LinkedIn job scraper adapter - main job source for FreshRoles.

This module provides job discovery via LinkedIn using Playwright and cookies
for authentication. Based on the react2shell-scanner approach.
"""

import os
import re
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from typing import Any

from freshroles.models.job import JobPosting
from freshroles.models.enums import ATSType, EmploymentType, RemoteType


# Default LinkedIn search URL for intern jobs
DEFAULT_SEARCH_URL = (
    "https://www.linkedin.com/jobs/search/?"
    "keywords=software%20engineer%20intern&"
    "location=United%20States&"
    "f_JT=I&"  # Internship filter
    "f_TPR=r86400"  # Last 24 hours
)


def add_time_filter(url: str, seconds: int = 86400) -> str:
    """Add time filter to LinkedIn search URL."""
    u = urlparse(url)
    q = parse_qs(u.query)
    q["f_TPR"] = [f"r{int(seconds)}"]
    
    # Sort by date descending
    if "sortBy" not in q:
        q["sortBy"] = ["DD"]
    
    return urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(q, doseq=True), u.fragment))


def extract_text(obj: Any) -> str:
    """Extract text from string or dict."""
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, dict):
        return obj.get("text", "").strip()
    return ""


class LinkedInScraper:
    """
    LinkedIn job scraper using Playwright.
    
    This is the main job source for FreshRoles, replacing individual
    company ATS scrapers with LinkedIn's aggregated job listings.
    """
    
    def __init__(
        self,
        cookies_path: str | Path = "cookies.json",
        profile_dir: str | Path = "linkedin_profile",
        headless: bool = True,
    ):
        """
        Initialize LinkedIn scraper.
        
        Args:
            cookies_path: Path to LinkedIn cookies JSON file.
            profile_dir: Path to Playwright browser profile directory.
            headless: Whether to run browser in headless mode.
        """
        self.cookies_path = Path(cookies_path)
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self._context = None
        self._playwright = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, *args):
        """Async context manager exit."""
        await self.close()
    
    async def close(self):
        """Close browser context."""
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
    
    def _load_cookies(self) -> list[dict]:
        """Load and format cookies for Playwright."""
        if not self.cookies_path.exists():
            return []
        
        try:
            with open(self.cookies_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            
            formatted = []
            for c in cookies:
                cookie = {
                    "name": c.get("name"),
                    "value": c.get("value"),
                    "domain": c.get("domain"),
                    "path": c.get("path", "/"),
                    "secure": c.get("secure", False),
                    "httpOnly": c.get("httpOnly", False),
                }
                if "expirationDate" in c:
                    cookie["expires"] = c["expirationDate"]
                if "sameSite" in c:
                    ss = c["sameSite"]
                    if ss == "no_restriction":
                        cookie["sameSite"] = "None"
                    elif ss in ["Strict", "Lax"]:
                        cookie["sameSite"] = ss
                    else:
                        cookie["sameSite"] = "None"
                formatted.append(cookie)
            return formatted
        except Exception as e:
            print(f"Error loading cookies: {e}")
            return []
    
    def search_sync(
        self,
        url: str | None = None,
        time_filter_seconds: int = 86400,
    ) -> list[JobPosting]:
        """
        Synchronously search LinkedIn for jobs.
        
        Args:
            url: LinkedIn search URL. Defaults to intern search.
            time_filter_seconds: Time filter in seconds (default 24h).
            
        Returns:
            List of JobPosting objects.
        """
        from playwright.sync_api import sync_playwright
        
        search_url = url or DEFAULT_SEARCH_URL
        search_url = add_time_filter(search_url, time_filter_seconds)
        
        jobs = []
        
        with sync_playwright() as p:
            # Check if profile exists for headless mode
            headless = self.headless and self.profile_dir.exists()
            
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=headless,
            )
            
            # Load cookies
            cookies = self._load_cookies()
            if cookies:
                context.add_cookies(cookies)
                print(f"Loaded {len(cookies)} cookies")
            
            # Set headers to avoid bot detection
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.linkedin.com/",
            }
            
            try:
                response = context.request.get(search_url, headers=headers, timeout=60000)
                
                if not response.ok:
                    print(f"LinkedIn request failed: {response.status}")
                    return []
                
                html = response.text()
                
                if "/jobs/view/" not in html:
                    print("No jobs found in response")
                    # Check for login issue
                    if "sign in" in html.lower() or "join now" in html.lower():
                        print("ERROR: LinkedIn requires login. Check cookies.json")
                    return []
                
                # Extract jobs from HTML
                raw_jobs = self._extract_jobs_from_html(html)
                
                # Convert to JobPosting objects
                for jid, title, company, link, extra in raw_jobs:
                    job = self._create_job_posting(jid, title, company, link, extra)
                    jobs.append(job)
                
                print(f"Found {len(jobs)} jobs from LinkedIn")
                
            except Exception as e:
                print(f"LinkedIn scrape error: {e}")
            finally:
                context.close()
        
        return jobs
    
    def _extract_jobs_from_html(self, html: str) -> list[tuple]:
        """
        Extract jobs from LinkedIn HTML.
        
        Returns list of (job_id, title, company, link, extra_data).
        """
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, "html.parser")
        jobs = {}
        
        # Strategy 1: DOM parsing
        anchors = soup.select("a[href*='/jobs/view/']")
        for a in anchors:
            href = a.get("href", "")
            m = re.search(r"/jobs/view/(\d+)", href)
            if not m:
                continue
            
            job_id = m.group(1)
            title = a.get_text(strip=True) or "LinkedIn Job"
            link = href if href.startswith("http") else "https://www.linkedin.com" + href
            
            # Try to find company
            company = ""
            try:
                container = a.find_parent("div")
                if container:
                    company_elem = container.select_one(
                        ".job-card-container__company-name, "
                        ".job-card-list__company-name, "
                        ".base-search-card__subtitle"
                    )
                    if company_elem:
                        company = company_elem.get_text(strip=True)
            except Exception:
                pass
            
            # Try to find location
            location = ""
            try:
                container = a.find_parent("li") or a.find_parent("div")
                if container:
                    loc_elem = container.select_one(
                        ".job-card-container__metadata-item, "
                        ".base-search-card__metadata, "
                        ".job-search-card__location"
                    )
                    if loc_elem:
                        location = loc_elem.get_text(strip=True)
            except Exception:
                pass
            
            extra = {"location": location}
            jobs[job_id] = (job_id, title, company, link, extra)
        
        if jobs:
            return list(jobs.values())
        
        # Strategy 2: Embedded JSON
        code_tags = soup.find_all("code")
        for code in code_tags:
            try:
                content = code.get_text(strip=True)
                if not content:
                    continue
                
                data = json.loads(content)
                entities = []
                
                if isinstance(data, dict):
                    if "included" in data:
                        entities.extend(data["included"])
                    if "data" in data and isinstance(data["data"], list):
                        entities.extend(data["data"])
                elif isinstance(data, list):
                    entities.extend(data)
                
                for entity in entities:
                    if not isinstance(entity, dict):
                        continue
                    
                    urn = entity.get("entityUrn") or entity.get("*jobPosting")
                    if not urn or "jobPosting" not in str(urn):
                        continue
                    
                    m = re.search(r"jobPosting(?:Card)?[:\(]\D*(\d+)", str(urn))
                    if not m:
                        continue
                    
                    job_id = m.group(1)
                    title = extract_text(entity.get("title")) or "LinkedIn Job"
                    company = extract_text(entity.get("primaryDescription"))
                    link = f"https://www.linkedin.com/jobs/view/{job_id}"
                    
                    # Extract more data
                    location = extract_text(entity.get("secondaryDescription", ""))
                    
                    extra = {
                        "location": location,
                        "salary": entity.get("salary"),
                        "insights": entity.get("insightText"),
                    }
                    
                    if job_id not in jobs or (company and not jobs[job_id][2]):
                        jobs[job_id] = (job_id, title, company, link, extra)
                
            except json.JSONDecodeError:
                continue
            except Exception:
                continue
        
        # Strategy 3: Regex fallback
        if not jobs:
            ids = re.findall(r"jobPosting(?:Card)?[:\(%]\D*(\d+)", html)
            for job_id in ids:
                if job_id not in jobs:
                    jobs[job_id] = (
                        job_id,
                        "LinkedIn Job",
                        "",
                        f"https://www.linkedin.com/jobs/view/{job_id}",
                        {},
                    )
        
        return list(jobs.values())
    
    def _create_job_posting(
        self,
        job_id: str,
        title: str,
        company: str,
        link: str,
        extra: dict,
    ) -> JobPosting:
        """Create a JobPosting from extracted data."""
        location = extra.get("location", "")
        
        # Detect remote type
        remote_type = RemoteType.UNKNOWN
        text_lower = f"{title} {location}".lower()
        if "remote" in text_lower:
            remote_type = RemoteType.REMOTE
        elif "hybrid" in text_lower:
            remote_type = RemoteType.HYBRID
        elif "on-site" in text_lower or "onsite" in text_lower:
            remote_type = RemoteType.ONSITE
        
        # Detect employment type
        employment_type = EmploymentType.FULL_TIME
        title_lower = title.lower()
        if "intern" in title_lower:
            employment_type = EmploymentType.INTERNSHIP
        elif "contract" in title_lower:
            employment_type = EmploymentType.CONTRACT
        
        return JobPosting(
            company=company or "Unknown",
            title=title,
            source_job_id=job_id,
            source_system=ATSType.UNKNOWN,  # LinkedIn aggregates many systems
            source_url="https://www.linkedin.com/jobs",
            apply_url=link,
            location=location or None,
            remote_type=remote_type,
            employment_type=employment_type,
            posted_at=datetime.now(timezone.utc),
            raw=extra,
        )


# Convenience function for CLI
def search_linkedin_jobs(
    query: str = "software engineer intern",
    location: str = "United States",
    time_hours: int = 24,
    cookies_path: str = "cookies.json",
) -> list[JobPosting]:
    """
    Search LinkedIn for jobs.
    
    Args:
        query: Job search query.
        location: Location filter.
        time_hours: How far back to search (in hours).
        cookies_path: Path to LinkedIn cookies.
        
    Returns:
        List of JobPosting objects.
    """
    import os
    from urllib.parse import quote_plus
    
    # Support LINKEDIN_SEARCH_URL env var like scanner.py
    env_url = os.getenv("LINKEDIN_SEARCH_URL")
    if env_url:
        url = env_url
        print(f"Using LINKEDIN_SEARCH_URL from env")
    else:
        # Build search URL with internship filter
        url = (
            f"https://www.linkedin.com/jobs/search/?"
            f"keywords={quote_plus(query)}&"
            f"location={quote_plus(location)}&"
            f"f_JT=I&"  # Internship filter
            f"f_TPR=r{time_hours * 3600}"
        )
    
    scraper = LinkedInScraper(cookies_path=cookies_path)
    return scraper.search_sync(url, time_filter_seconds=time_hours * 3600)
