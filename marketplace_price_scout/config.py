"""Configuration loading (env vars + optional config.json).

Precedence: environment variables > config.json > built-in defaults.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class ScoutConfig:
    """Runtime configuration for the scraper service."""

    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False
    timeout: float = 15.0
    max_retries: int = 2
    retry_backoff: float = 1.5
    rate_limit_delay: float = 0.0
    min_price_threshold: float = 50.0
    trim_percent: float = 0.15
    max_results: int = 100
    api_rate_limit_per_minute: int = 10
    ratelimit_storage_uri: str = "memory://"
    log_max_entries: int = 1000
    log_level: str = "INFO"
    warmup_cookies: bool = True
    use_curl_cffi: bool = True
    platforms: dict = field(default_factory=lambda: {
        "kleinanzeigen": True,
        "ebay": True,
        "vinted": True,
        "mydealz": True,
        "amazon": True,
        "hardwareschotte": True,
    })

    @classmethod
    def from_env(cls, config_path: str | Path | None = None) -> "ScoutConfig":
        cfg = cls()
        # 1) optional config.json
        path = Path(config_path) if config_path else Path("config.json")
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                flask = data.get("flask", {})
                scraper = data.get("scraper", {})
                pricing = data.get("pricing", {})
                api = data.get("api", {})
                platforms = data.get("platforms", {})
                if "host" in flask:
                    cfg.host = str(flask["host"])
                if "port" in flask:
                    cfg.port = int(flask["port"])
                if "debug" in flask:
                    cfg.debug = bool(flask["debug"])
                if "timeout" in scraper:
                    cfg.timeout = float(scraper["timeout"])
                if "max_retries" in scraper:
                    cfg.max_retries = int(scraper["max_retries"])
                if "trim_percent" in pricing:
                    cfg.trim_percent = float(pricing["trim_percent"])
                if "min_price_threshold" in pricing:
                    cfg.min_price_threshold = float(pricing["min_price_threshold"])
                if "rate_limit_per_minute" in api:
                    cfg.api_rate_limit_per_minute = int(api["rate_limit_per_minute"])
                if "max_results" in api:
                    cfg.max_results = int(api["max_results"])
                for key, val in platforms.items():
                    clean = key.replace("_enabled", "")
                    if clean in cfg.platforms:
                        cfg.platforms[clean] = bool(val)
            except Exception:
                pass  # broken config.json must never prevent startup

        # 2) environment overrides
        cfg.host = os.getenv("FLASK_HOST", cfg.host)
        cfg.port = _env_int("FLASK_PORT", cfg.port)
        cfg.debug = _env_bool("FLASK_DEBUG", cfg.debug)
        cfg.timeout = _env_float("SCRAPER_TIMEOUT", cfg.timeout)
        cfg.max_retries = _env_int("SCRAPER_MAX_RETRIES", cfg.max_retries)
        cfg.api_rate_limit_per_minute = _env_int(
            "API_RATE_LIMIT_PER_MINUTE", cfg.api_rate_limit_per_minute
        )
        cfg.max_results = _env_int("API_MAX_RESULTS", cfg.max_results)
        cfg.ratelimit_storage_uri = os.getenv(
            "RATELIMIT_STORAGE_URI", cfg.ratelimit_storage_uri
        )
        cfg.log_level = os.getenv("LOG_LEVEL", cfg.log_level).upper()
        cfg.warmup_cookies = _env_bool("SCRAPER_WARMUP", cfg.warmup_cookies)
        cfg.use_curl_cffi = _env_bool("SCRAPER_USE_CURL_CFFI", cfg.use_curl_cffi)
        return cfg


# Backwards-compatible dict-style access used by the legacy app.py shim.
def as_dict(cfg: ScoutConfig) -> dict:
    return {
        "timeout": cfg.timeout,
        "rate_limit": cfg.rate_limit_delay,
        "max_retries": cfg.max_retries,
        "min_price_threshold": cfg.min_price_threshold,
        "trim_percent": cfg.trim_percent,
        "max_results": cfg.max_results,
    }
