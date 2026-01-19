"""Rate-limited HTTP client with retry logic."""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from freshroles.models.enums import AdapterErrorType
from freshroles.adapters.base import AdapterError


class RateLimiter:
    """Per-domain rate limiter."""
    
    def __init__(self, default_rps: float = 1.0):
        self.default_rps = default_rps
        self._domain_limits: dict[str, float] = {}
        self._last_request: dict[str, datetime] = defaultdict(lambda: datetime.min)
        self._lock = asyncio.Lock()
    
    def set_limit(self, domain: str, rps: float):
        """Set rate limit for a specific domain."""
        self._domain_limits[domain] = rps
    
    async def acquire(self, url: str):
        """Wait until rate limit allows the request."""
        domain = urlparse(url).netloc
        rps = self._domain_limits.get(domain, self.default_rps)
        min_interval = timedelta(seconds=1.0 / rps)
        
        async with self._lock:
            elapsed = datetime.now() - self._last_request[domain]
            if elapsed < min_interval:
                wait_time = (min_interval - elapsed).total_seconds()
                await asyncio.sleep(wait_time)
            self._last_request[domain] = datetime.now()


class HTTPClient:
    """HTTP client with rate limiting, retries, and caching."""
    
    DEFAULT_HEADERS = {
        "User-Agent": "FreshRoles/0.1 (Job Discovery Bot; +https://github.com/freshroles)",
        "Accept": "application/json, text/html",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    def __init__(self, rate_limiter: RateLimiter | None = None):
        self.rate_limiter = rate_limiter or RateLimiter()
        self._client: httpx.AsyncClient | None = None
        self._etag_cache: dict[str, str] = {}
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            headers=self.DEFAULT_HEADERS,
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        )
        return self
    
    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
    
    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def get(
        self,
        url: str,
        headers: dict | None = None,
        use_cache: bool = True,
    ) -> httpx.Response:
        """
        Make a GET request with rate limiting and retries.
        
        Args:
            url: URL to fetch.
            headers: Additional headers.
            use_cache: Whether to use ETag caching.
            
        Returns:
            HTTP response.
            
        Raises:
            AdapterError: On request failure.
        """
        await self.rate_limiter.acquire(url)
        
        request_headers = dict(headers or {})
        if use_cache and url in self._etag_cache:
            request_headers["If-None-Match"] = self._etag_cache[url]
        
        try:
            response = await self._client.get(url, headers=request_headers)
            
            if response.status_code == 304:
                return response
            
            if "ETag" in response.headers:
                self._etag_cache[url] = response.headers["ETag"]
            
            if response.status_code == 429:
                raise AdapterError(
                    f"Rate limited by {url}",
                    error_type=AdapterErrorType.RATE_LIMITED,
                )
            
            if response.status_code == 401:
                raise AdapterError(
                    f"Unauthorized access to {url}",
                    error_type=AdapterErrorType.UNAUTHORIZED,
                )
            
            if response.status_code == 403:
                raise AdapterError(
                    f"Forbidden access to {url}",
                    error_type=AdapterErrorType.BLOCKED_BY_ROBOTS,
                )
            
            response.raise_for_status()
            return response
            
        except httpx.TimeoutException as e:
            raise AdapterError(
                f"Timeout fetching {url}",
                error_type=AdapterErrorType.TIMEOUT,
                details={"error": str(e)},
            )
        except httpx.TransportError as e:
            raise AdapterError(
                f"Network error fetching {url}",
                error_type=AdapterErrorType.NETWORK_ERROR,
                details={"error": str(e)},
            )
    
    async def get_json(self, url: str, headers: dict | None = None) -> dict:
        """Fetch JSON from URL."""
        response = await self.get(url, headers=headers)
        return response.json()
    
    async def get_html(self, url: str, headers: dict | None = None) -> str:
        """Fetch HTML from URL."""
        response = await self.get(url, headers=headers)
        return response.text
