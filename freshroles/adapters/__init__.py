"""FreshRoles adapters."""

from freshroles.adapters.base import AdapterError, AdapterStatus, BaseAdapter
from freshroles.adapters.registry import AdapterRegistry
from freshroles.adapters.detector import ATSDetector
from freshroles.adapters.generic import GenericHTMLAdapter

# Import adapters to register them
from freshroles.adapters import greenhouse, lever, workday, ashby, smartrecruiters

__all__ = [
    "AdapterError",
    "AdapterStatus",
    "BaseAdapter",
    "AdapterRegistry",
    "ATSDetector",
    "GenericHTMLAdapter",
]
