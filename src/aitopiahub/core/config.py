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
    account_handle: str = "aitopiahub_kids"
    kids_run_slots: str = "10:00,19:00"
    kids_retry_budget: int = 2
    automation_strict_free: bool = True
    hybrid_daily_mix: str = "1_fairy_1_demand"
    fairy_style: str = "modern_educational"
    fairy_library_path: str = "./configs/fairy_tales.yaml"
    slot1_mode: str = "fairy_tale"
    slot2_mode: str = "demand_driven"

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

    # TTS runtime routing
    tts_provider_premium: str = "elevenlabs"
    tts_provider_primary: str = "xtts_local"
    tts_provider_secondary: str = "edge"
    tts_provider_fallback: str = "piper"
    xtts_model_path: str = ""
    xtts_device: str = "cpu"
    xtts_binary: str = "tts"
    piper_binary: str = "piper"
    piper_model_tr_path: str = ""
    piper_model_en_path: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_tr: str = ""
    elevenlabs_voice_en: str = ""
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_cost_per_1k_chars: float = 0.30

    # Visual runtime routing
    visual_provider_primary: str = "pexels"
    visual_provider_secondary: str = "pixabay"
    visual_provider_ai: str = "pollinations"
    pexels_api_key: str = ""
    pixabay_api_key: str = ""

    # Music + quality gate
    music_pool_manifest: str = "assets/music/kids_pool/music_manifest.json"
    quality_gate_strict: bool = True
    quality_min_audio: float = 0.60
    quality_min_visual: float = 0.50
    quality_min_music: float = 0.60
    quality_min_technical: float = 0.70

    # Optional paid quality mode
    allow_premium_models: bool = False
    max_cost_per_video_usd: float = 5.0

    # Feature flags
    enable_shorts_pipeline: bool = False

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
