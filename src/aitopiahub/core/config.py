"""
Üç katmanlı config sistemi:
  1. configs/base.yaml          → global defaults
  2. configs/accounts/{x}.yaml  → hesap-özel overrides
  3. Environment variables       → secrets + deployment (her zaman kazanır)
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[3]
CONFIGS_DIR = BASE_DIR / "configs"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


class LLMConfig:
    generation_model: str = "llama-3.3-70b-versatile"
    fast_model: str = "llama-3.1-8b-instant"
    max_tokens: int = 600
    temperature: float = 0.85


class SchedulingConfig:
    default_posts_per_day: int = 8
    posting_window_start: str = "07:00"
    posting_window_end: str = "23:00"
    min_gap_minutes: int = 60
    peak_hours: list[int] = [9, 12, 17, 20, 22]


class TrendConfig:
    fetch_interval_minutes: int = 15
    min_trend_score: float = 0.35
    max_trends_per_cycle: int = 10
    trend_ttl_hours: int = 6


class ContentConfig:
    min_quality_score: int = 75
    min_safety_score: int = 85
    ab_test_ratio: float = 0.3
    duplicate_similarity_threshold: float = 0.88
    max_revision_iterations: int = 2


class ImageConfig:
    generate_probability: float = 0.65
    carousel_max_slides: int = 7
    carousel_min_slides: int = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "development"
    secret_key: str = "changeme"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://aitopiahub:aitopiahub@localhost:5432/aitopiahub"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Groq
    groq_api_key: str = ""

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # YouTube
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""

    # Instagram
    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    instagram_access_token: str = ""
    instagram_business_account_id: str = ""

    # Reddit
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "aitopiahub/1.0"

    # NewsAPI
    newsapi_key: str = ""

    # Storage
    storage_type: str = "local"
    storage_local_path: str = "./data/images"
    public_base_url: str = "http://localhost:8000"

    # Admin
    admin_api_key: str = "changeme"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


class AccountConfig:
    """Birleştirilmiş hesap konfigürasyonu (YAML + env overrides)."""

    def __init__(self, account_handle: str):
        self.handle = account_handle

        base = _load_yaml(CONFIGS_DIR / "base.yaml")
        account = _load_yaml(CONFIGS_DIR / "accounts" / f"{account_handle}.yaml")
        merged = _deep_merge(base, account)

        # Hesap özellikleri
        self.niche: str = merged.get("niche", "news")
        self.language_primary: str = merged.get("language_primary", "tr")
        self.language_secondary: str = merged.get("language_secondary", "en")
        self.timezone: str = merged.get("timezone", "Europe/Istanbul")

        # Alt config objeleri
        sched = merged.get("scheduling", {})
        self.posts_per_day: int = sched.get("default_posts_per_day", 8)
        self.posting_window_start: str = sched.get("posting_window_start", "07:00")
        self.posting_window_end: str = sched.get("posting_window_end", "23:00")
        self.min_gap_minutes: int = sched.get("min_gap_minutes", 60)
        self.peak_hours: list[int] = sched.get("peak_hours", [9, 12, 17, 20, 22])
        self.strict_peak_hours: bool = bool(sched.get("strict_peak_hours", True))
        self.bootstrap_hours: int = int(sched.get("bootstrap_hours", 48))
        self.bootstrap_posts_per_day: int = int(sched.get("bootstrap_posts_per_day", 4))

        trend = merged.get("trend_engine", {})
        self.trend_fetch_interval: int = trend.get("fetch_interval_minutes", 15)
        self.min_trend_score: float = trend.get("min_trend_score", 0.35)
        self.max_trends_per_cycle: int = trend.get("max_trends_per_cycle", 5)

        content = merged.get("content_engine", {})
        self.min_quality_score: int = content.get("min_quality_score", 75)
        self.ab_test_ratio: float = content.get("ab_test_ratio", 0.3)
        self.dedup_threshold: float = content.get("duplicate_similarity_threshold", 0.88)
        self.min_publish_quality_score: int = content.get("min_publish_quality_score", 78)

        img = merged.get("image", {})
        self.image_generate_prob: float = img.get("generate_probability", 0.65)
        self.image_style_preset: str = img.get("style_preset", "tech_modern")

        llm = merged.get("llm", {})
        self.llm_system_prompt_variant: str = llm.get("system_prompt_variant", "news_authoritative")

        monetization = merged.get("monetization", {})
        self.monetization_enabled: bool = bool(monetization.get("enabled", True))
        self.affiliate_ratio_max: float = float(monetization.get("affiliate_ratio_max", 0.3))
        self.min_quality_for_affiliate: int = int(monetization.get("min_quality_for_affiliate", 82))
        self.default_utm_campaign: str = monetization.get("default_utm_campaign", "aitopiahub_launch")
        self.requires_manual_approval_days: int = int(monetization.get("requires_manual_approval_days", 14))
        self.signup_value_estimate: float = float(monetization.get("signup_value_estimate", 2.5))

        topics = merged.get("topics", {})
        self.seed_keywords: list[str] = topics.get("seed_keywords", [])
        self.blocked_keywords: list[str] = topics.get("blocked_keywords", [])

        # Hesap-özel Instagram credentials (env overlay'den)
        env_file = BASE_DIR / ".env.accounts" / f"{account_handle}.env"
        self._load_account_env(env_file)

    def _load_account_env(self, env_file: Path) -> None:
        if not env_file.exists():
            return
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

    @staticmethod
    @lru_cache(maxsize=None)
    def for_account(handle: str) -> "AccountConfig":
        return AccountConfig(handle)
