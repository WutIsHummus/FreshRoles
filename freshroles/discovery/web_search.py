"""Web search-based job discovery.

This module provides job discovery via web search engines,
not limited to specific company career pages.
"""

import re
import hashlib
from datetime import datetime, timezone
from typing import Any


async def search_jobs_web(
    query: str = "software engineer intern",
    location: str = "United States",
    num_results: int = 50,
) -> list[dict[str, Any]]:
    """
    Search for jobs using web search.
    
    This searches across the entire web for job postings matching
    the query, not limited to specific company ATS systems.
    
    Args:
        query: Job search query
        location: Location filter
        num_results: Maximum results to return
        
    Returns:
        List of job dictionaries with title, company, url, etc.
    """
    import httpx
    
    jobs = []
    
    # DuckDuckGo HTML search (no API key needed)
    search_query = f"{query} {location} site:linkedin.com/jobs OR site:indeed.com OR site:glassdoor.com"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # Search DuckDuckGo
        ddg_url = f"https://html.duckduckgo.com/html/?q={search_query.replace(' ', '+')}"
        
        try:
            resp = await client.get(ddg_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            
            if resp.status_code == 200:
                jobs.extend(_parse_ddg_results(resp.text, location))
        except Exception:
            pass
    
    return jobs[:num_results]


def _parse_ddg_results(html: str, location: str) -> list[dict]:
    """Parse DuckDuckGo search results for job postings."""
    jobs = []
    
    # Find result links
    pattern = r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
    matches = re.findall(pattern, html, re.I)
    
    for url, title in matches:
        # Filter for job-related URLs
        if not any(site in url.lower() for site in ['linkedin.com/jobs', 'indeed.com', 'glassdoor.com', 'greenhouse.io', 'lever.co']):
            continue
        
        # Clean up the title
        title = re.sub(r'\s+', ' ', title).strip()
        
        # Try to extract company from title or URL
        company = "Unknown"
        if " at " in title:
            parts = title.split(" at ")
            title = parts[0].strip()
            company = parts[1].strip() if len(parts) > 1 else "Unknown"
        elif " - " in title:
            parts = title.split(" - ")
            if len(parts) >= 2:
                title = parts[0].strip()
                company = parts[1].strip()
        
        job_id = hashlib.md5(url.encode()).hexdigest()[:12]
        
        jobs.append({
            "id": job_id,
            "title": title,
            "company": company,
            "location": location,
            "url": url,
            "source": "web_search",
            "found_at": datetime.now(timezone.utc).isoformat(),
        })
    
    return jobs


async def search_intern_jobs_usa(role: str = "software engineer") -> list[dict]:
    """
    Convenience function to search for intern jobs in the USA.
    
    Args:
        role: Base role to search for (e.g., "software engineer", "data scientist")
        
    Returns:
        List of intern job postings.
    """
    queries = [
        f"{role} intern United States",
        f"{role} internship USA remote",
        f"{role} intern California Texas",
        f"{role} summer intern 2024 2025",
    ]
    
    all_jobs = []
    seen_urls = set()
    
    for query in queries:
        jobs = await search_jobs_web(query, "United States", 25)
        for job in jobs:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)
    
    return all_jobs


# CLI integration
async def run_web_search_scan(output_file: str | None = None):
    """Run a web search scan for intern jobs."""
    print("Searching the web for intern jobs...")
    print("(This searches LinkedIn, Indeed, Glassdoor, and more)\n")
    
    jobs = await search_intern_jobs_usa("software engineer")
    
    print(f"Found {len(jobs)} jobs:\n")
    
    for i, job in enumerate(jobs[:20], 1):
        print(f"{i:2}. {job['title'][:50]}")
        print(f"    Company: {job['company']}")
        print(f"    URL: {job['url'][:80]}...")
        print()
    
    if output_file:
        import json
        with open(output_file, "w") as f:
            json.dump(jobs, f, indent=2)
        print(f"\nSaved {len(jobs)} jobs to {output_file}")
    
    return jobs


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_web_search_scan("web_search_jobs.json"))
