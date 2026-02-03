"""
Configuration management for the Abbreviation Module.

Provides flexible configuration with environment variable support and sensible defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class CacheConfig:
    """Cache configuration settings."""
    
    enabled: bool = True
    ttl_seconds: int = 3600  # 1 hour default
    max_size: int = 1000  # Maximum cached entries
    
    @classmethod
    def from_env(cls) -> "CacheConfig":
        """Create configuration from environment variables."""
        return cls(
            enabled=os.getenv("ABBREVIATION_CACHE_ENABLED", "true").lower() == "true",
            ttl_seconds=int(os.getenv("ABBREVIATION_CACHE_TTL", "3600")),
            max_size=int(os.getenv("ABBREVIATION_CACHE_MAX_SIZE", "1000")),
        )


@dataclass
class AbbreviationConfig:
    """Main configuration for the Abbreviation Module."""
    
    cache: CacheConfig = field(default_factory=CacheConfig)
    
    # Fallback abbreviations when database lookup fails
    fallback_abbreviations: Dict[str, str] = field(default_factory=dict)
    
    # Whether to raise exception or use fallback when abbreviation not found
    raise_on_not_found: bool = True
    
    # Default abbreviation to use when not found and raise_on_not_found is False
    default_abbreviation: str = "DOC"
    
    @classmethod
    def from_env(cls) -> "AbbreviationConfig":
        """Create configuration from environment variables."""
        return cls(
            cache=CacheConfig.from_env(),
            raise_on_not_found=os.getenv("ABBREVIATION_RAISE_ON_NOT_FOUND", "true").lower() == "true",
            default_abbreviation=os.getenv("ABBREVIATION_DEFAULT", "DOC"),
        )
    
    def validate(self) -> None:
        """Validate configuration values.
        
        Raises:
            AbbreviationConfigError: If configuration is invalid.
        """
        from abbreviation_module.exceptions import AbbreviationConfigError
        
        if self.cache.ttl_seconds < 0:
            raise AbbreviationConfigError("Cache TTL must be non-negative")
        
        if self.cache.max_size < 1:
            raise AbbreviationConfigError("Cache max size must be at least 1")
        
        if not self.default_abbreviation:
            raise AbbreviationConfigError("Default abbreviation cannot be empty")
        
        if len(self.default_abbreviation) > 10:
            raise AbbreviationConfigError("Default abbreviation must be 10 characters or less")


# Global default configuration instance
_default_config: Optional[AbbreviationConfig] = None


def get_config() -> AbbreviationConfig:
    """Get the global configuration instance.
    
    Returns:
        AbbreviationConfig: The current configuration.
    """
    global _default_config
    if _default_config is None:
        _default_config = AbbreviationConfig.from_env()
    return _default_config


def set_config(config: AbbreviationConfig) -> None:
    """Set the global configuration instance.
    
    Args:
        config: The configuration to use.
    """
    global _default_config
    config.validate()
    _default_config = config
