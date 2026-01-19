"""Enumeration types for FreshRoles."""

from enum import Enum


class RemoteType(str, Enum):
    """Remote work type classification."""
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class EmploymentType(str, Enum):
    """Employment type classification."""
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    UNKNOWN = "unknown"


class ATSType(str, Enum):
    """Applicant Tracking System types."""
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"
    ICIMS = "icims"
    SMARTRECRUITERS = "smartrecruiters"
    SUCCESSFACTORS = "successfactors"
    TALEO = "taleo"
    ASHBY = "ashby"
    UNKNOWN = "unknown"


class AdapterErrorType(str, Enum):
    """Error types for adapter operations."""
    BLOCKED_BY_ROBOTS = "blocked_by_robots"
    UNAUTHORIZED = "unauthorized"
    RATE_LIMITED = "rate_limited"
    PARSE_ERROR = "parse_error"
    SCHEMA_CHANGE_SUSPECTED = "schema_change_suspected"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"
