"""Configuration loading utilities."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings

from freshroles.models.company import CompanyConfig, MatchingProfile


class Settings(BaseSettings):
    """Application settings loaded from environment."""
    
    db_path: str = "freshroles.db"
    config_dir: str = "configs"
    
    # Notification settings
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"
    
    # Embedding settings
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    
    # Rate limiting
    default_rps: float = 1.0
    
    class Config:
        env_prefix = "FRESHROLES_"
        env_file = ".env"


def load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML file."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_company_config(path: Path) -> CompanyConfig:
    """Load company config from YAML file."""
    data = load_yaml(path)
    return CompanyConfig(**data)


def load_matching_profile(path: Path) -> MatchingProfile:
    """Load matching profile from YAML file."""
    data = load_yaml(path)
    return MatchingProfile(**data)


def load_all_companies(config_dir: Path) -> list[CompanyConfig]:
    """Load all company configs from a directory."""
    companies = []
    companies_dir = config_dir / "companies"
    
    if companies_dir.exists():
        for yaml_file in companies_dir.glob("*.yaml"):
            try:
                company = load_company_config(yaml_file)
                companies.append(company)
            except Exception:
                pass
        for yaml_file in companies_dir.glob("*.yml"):
            try:
                company = load_company_config(yaml_file)
                companies.append(company)
            except Exception:
                pass
    
    return companies


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
