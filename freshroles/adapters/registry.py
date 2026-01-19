"""Adapter registry and auto-detection."""

from freshroles.adapters.base import BaseAdapter
from freshroles.models.enums import ATSType


class AdapterRegistry:
    """Registry for ATS adapters."""
    
    _adapters: dict[ATSType, type[BaseAdapter]] = {}
    _instances: dict[ATSType, BaseAdapter] = {}
    
    @classmethod
    def register(cls, ats_type: ATSType):
        """Decorator to register an adapter class."""
        def decorator(adapter_cls: type[BaseAdapter]):
            adapter_cls.ats_type = ats_type
            cls._adapters[ats_type] = adapter_cls
            return adapter_cls
        return decorator
    
    @classmethod
    def get(cls, ats_type: ATSType) -> BaseAdapter | None:
        """Get an adapter instance for the given ATS type."""
        if ats_type not in cls._instances:
            adapter_cls = cls._adapters.get(ats_type)
            if adapter_cls:
                cls._instances[ats_type] = adapter_cls()
        return cls._instances.get(ats_type)
    
    @classmethod
    def get_all(cls) -> list[BaseAdapter]:
        """Get all registered adapter instances."""
        return [cls.get(ats_type) for ats_type in cls._adapters if cls.get(ats_type)]
    
    @classmethod
    def supported_types(cls) -> list[ATSType]:
        """Get list of supported ATS types."""
        return list(cls._adapters.keys())
