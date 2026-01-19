"""Tests for Greenhouse adapter."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from freshroles.adapters.greenhouse import GreenhouseAdapter
from freshroles.models.company import CompanyConfig
from freshroles.models.enums import ATSType, EmploymentType, RemoteType


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def greenhouse_jobs_response():
    """Load Greenhouse jobs fixture."""
    with open(FIXTURES_DIR / "greenhouse_jobs.json") as f:
        return json.load(f)


@pytest.fixture
def company_config():
    """Create test company config."""
    return CompanyConfig(
        name="TestCompany",
        career_urls=["https://boards.greenhouse.io/testcompany"],
        ats_type=ATSType.GREENHOUSE,
    )


@pytest.fixture
def mock_http_client(greenhouse_jobs_response):
    """Create mock HTTP client."""
    client = MagicMock()
    client.get_json = AsyncMock(return_value=greenhouse_jobs_response)
    return client


class TestGreenhouseAdapter:
    """Tests for GreenhouseAdapter."""
    
    def test_supports_url(self):
        """Test URL support detection."""
        adapter = GreenhouseAdapter()
        
        assert adapter.supports_url("https://boards.greenhouse.io/stripe")
        assert adapter.supports_url("https://boards.greenhouse.io/airbnb/jobs/123")
        assert not adapter.supports_url("https://jobs.lever.co/figma")
        assert not adapter.supports_url("https://example.com/careers")
    
    def test_extract_board_token(self):
        """Test board token extraction."""
        adapter = GreenhouseAdapter()
        
        assert adapter._extract_board_token("https://boards.greenhouse.io/stripe") == "stripe"
        assert adapter._extract_board_token("https://boards.greenhouse.io/airbnb/jobs/123") == "airbnb"
        assert adapter._extract_board_token("https://example.com") is None
    
    @pytest.mark.asyncio
    async def test_discover(self, company_config, mock_http_client):
        """Test job discovery."""
        adapter = GreenhouseAdapter(http_client=mock_http_client)
        
        jobs = await adapter.discover(company_config)
        
        assert len(jobs) == 3
        assert jobs[0].title == "Software Engineer Intern"
        assert jobs[0].company == "TestCompany"
        assert jobs[0].source_system == ATSType.GREENHOUSE
    
    @pytest.mark.asyncio
    async def test_discover_with_filters(self, greenhouse_jobs_response, mock_http_client):
        """Test job discovery with deny filters."""
        config = CompanyConfig(
            name="TestCompany",
            career_urls=["https://boards.greenhouse.io/testcompany"],
            deny_filters=["Senior"],
        )
        
        adapter = GreenhouseAdapter(http_client=mock_http_client)
        jobs = await adapter.discover(config)
        
        # Should filter out "Senior Software Engineer"
        assert len(jobs) == 2
        assert not any("Senior" in j.title for j in jobs)
    
    def test_detect_remote_type(self):
        """Test remote type detection."""
        adapter = GreenhouseAdapter()
        
        assert adapter._detect_remote_type("Engineer", "Remote") == RemoteType.REMOTE
        assert adapter._detect_remote_type("Remote Engineer", None) == RemoteType.REMOTE
        assert adapter._detect_remote_type("Engineer", "San Francisco (Hybrid)") == RemoteType.HYBRID
        assert adapter._detect_remote_type("On-site Engineer", "NYC") == RemoteType.ONSITE
        assert adapter._detect_remote_type("Engineer", "NYC") == RemoteType.UNKNOWN
    
    def test_detect_employment_type(self):
        """Test employment type detection."""
        adapter = GreenhouseAdapter()
        
        assert adapter._detect_employment_type("Software Engineer Intern") == EmploymentType.INTERNSHIP
        assert adapter._detect_employment_type("Contract Engineer") == EmploymentType.CONTRACT
        assert adapter._detect_employment_type("Part-time Developer") == EmploymentType.PART_TIME
        assert adapter._detect_employment_type("Software Engineer") == EmploymentType.FULL_TIME
