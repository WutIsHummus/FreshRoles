"""ATS type auto-detection from URLs and HTML content."""

import re
from urllib.parse import urlparse

from freshroles.models.enums import ATSType


# URL patterns for ATS detection
URL_PATTERNS: dict[ATSType, list[re.Pattern]] = {
    ATSType.GREENHOUSE: [
        re.compile(r"boards\.greenhouse\.io", re.I),
        re.compile(r"job-boards\.greenhouse\.io", re.I),
    ],
    ATSType.LEVER: [
        re.compile(r"jobs\.lever\.co", re.I),
        re.compile(r"lever\.co/[^/]+/jobs", re.I),
    ],
    ATSType.WORKDAY: [
        re.compile(r"myworkdayjobs\.com", re.I),
        re.compile(r"wd\d+\.myworkday\.com", re.I),
        re.compile(r"workday\.com/.*careers", re.I),
    ],
    ATSType.ICIMS: [
        re.compile(r"icims\.com", re.I),
        re.compile(r"careers-.*\.icims\.com", re.I),
    ],
    ATSType.SMARTRECRUITERS: [
        re.compile(r"smartrecruiters\.com", re.I),
        re.compile(r"jobs\.smartrecruiters\.com", re.I),
    ],
    ATSType.SUCCESSFACTORS: [
        re.compile(r"successfactors\.", re.I),
        re.compile(r"jobs\.sap\.com", re.I),
    ],
    ATSType.TALEO: [
        re.compile(r"taleo\.net", re.I),
        re.compile(r"oraclecloud\.com.*hcm", re.I),
    ],
    ATSType.ASHBY: [
        re.compile(r"jobs\.ashbyhq\.com", re.I),
        re.compile(r"ashbyhq\.com/[^/]+/jobs", re.I),
    ],
}

# HTML content patterns for ATS detection
HTML_PATTERNS: dict[ATSType, list[re.Pattern]] = {
    ATSType.GREENHOUSE: [
        re.compile(r"greenhouse\.io", re.I),
        re.compile(r"grnhse_app", re.I),
    ],
    ATSType.LEVER: [
        re.compile(r"lever-jobs-iframe", re.I),
        re.compile(r"lever\.co", re.I),
    ],
    ATSType.WORKDAY: [
        re.compile(r"workday", re.I),
        re.compile(r"wd-", re.I),
    ],
    ATSType.ICIMS: [
        re.compile(r"icims", re.I),
    ],
    ATSType.SMARTRECRUITERS: [
        re.compile(r"smartrecruiters", re.I),
    ],
    ATSType.ASHBY: [
        re.compile(r"ashbyhq", re.I),
    ],
}


class ATSDetector:
    """Detect ATS type from URLs and HTML content."""
    
    def detect_from_url(self, url: str) -> ATSType:
        """
        Detect ATS type from URL patterns.
        
        Args:
            url: Career page URL to analyze.
            
        Returns:
            Detected ATS type or UNKNOWN.
        """
        parsed = urlparse(url)
        full_url = f"{parsed.netloc}{parsed.path}"
        
        for ats_type, patterns in URL_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(full_url):
                    return ats_type
        
        return ATSType.UNKNOWN
    
    def detect_from_html(self, html: str) -> ATSType:
        """
        Detect ATS type from HTML content patterns.
        
        Args:
            html: HTML content to analyze.
            
        Returns:
            Detected ATS type or UNKNOWN.
        """
        # Look for script tags and common markers
        for ats_type, patterns in HTML_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(html):
                    return ats_type
        
        return ATSType.UNKNOWN
    
    def detect(self, url: str, html: str | None = None) -> tuple[ATSType, float]:
        """
        Detect ATS type with confidence score.
        
        Args:
            url: Career page URL.
            html: Optional HTML content for additional detection.
            
        Returns:
            Tuple of (detected ATS type, confidence 0.0-1.0).
        """
        url_result = self.detect_from_url(url)
        
        if url_result != ATSType.UNKNOWN:
            return url_result, 0.95
        
        if html:
            html_result = self.detect_from_html(html)
            if html_result != ATSType.UNKNOWN:
                return html_result, 0.7
        
        return ATSType.UNKNOWN, 0.0
