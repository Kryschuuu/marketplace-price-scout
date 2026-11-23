"""Configuration loading (env vars + optional config.json).

Precedence: environment variables > config.json > built-in defaults.

Every numeric setting is clamped to a sane range so that a typo in
``config.json`` or a bogus environment variable can never produce an
unusable (e.g. zero-timeout) service.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

_module_log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

PLATFORM_NAMES: tuple[str, ...] = (
    "kleinanzeigen",
    "ebay",
    "vinted",
    "mydealz",
    "amazon",
    "hardwareschotte",
)

# Platforms that actually produce search results. ``hardwareschotte`` only
# provides a reference price, which is why it is not listed here.
RESULT_PLATFORMS: tuple[str, ...] = (
    "kleinanzeigen",
    "ebay",
    "vinted",
    "mydealz",
    "amazon",
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        _module_log.warning("Ignoring invalid integer for %s: %r", name, raw)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        _module_log.warning("Ignoring invalid float for %s: %r", name, raw)
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _as_bool(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _as_number(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


@dataclass
class ScoutConfig:
    """Runtime configuration for the scraper service."""

    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False
    # HTTP client / scraping behaviour
    timeout: float = 15.0
    max_retries: int = 2
    retry_backoff: float = 1.5
    rate_limit_delay: float = 0.0
    scrape_deadline: float = 25.0
    user_agent: str = DEFAULT_USER_AGENT
    # Price analysis
    min_price_threshold: float = 50.0
    trim_percent: float = 0.15
    max_results: int = 100
    # API / limits
    api_rate_limit_per_minute: int = 10
    log_rate_limit_per_minute: int = 120
    log_clear_rate_limit_per_minute: int = 30
    ratelimit_storage_uri: str = "memory://"
    cors_origins: tuple[str, ...] = ()
    # Logging
    log_max_entries: int = 1000
    log_level: str = "INFO"
    # Client selection
    warmup_cookies: bool = True
    use_curl_cffi: bool = True
    platforms: dict = field(
        default_factory=lambda: {name: True for name in PLATFORM_NAMES}
    )

    def __post_init__(self) -> None:
        self.normalize()

    def normalize(self) -> None:
        """Clamp/validate every field so the service stays usable."""
        self.port = int(_clamp(_as_number(self.port, 5000), 1, 65535))
        self.timeout = float(_clamp(_as_number(self.timeout, 15.0), 1.0, 120.0))
        self.max_retries = int(_clamp(_as_number(self.max_retries, 2), 0, 5))
        self.retry_backoff = float(
            _clamp(_as_number(self.retry_backoff, 1.5), 0.0, 10.0)
        )
        self.rate_limit_delay = float(
            _clamp(_as_number(self.rate_limit_delay, 0.0), 0.0, 10.0)
        )
        self.scrape_deadline = float(
            _clamp(_as_number(self.scrape_deadline, 25.0), 1.0, 300.0)
        )
        self.min_price_threshold = float(
            _clamp(_as_number(self.min_price_threshold, 50.0), 0.0, 1_000_000.0)
        )
        self.trim_percent = float(
            _clamp(_as_number(self.trim_percent, 0.15), 0.0, 0.49)
        )
        self.max_results = int(
            _clamp(_as_number(self.max_results, 100), 1, 1000)
        )
        self.api_rate_limit_per_minute = int(
            _clamp(_as_number(self.api_rate_limit_per_minute, 10), 1, 100_000)
        )
        self.log_rate_limit_per_minute = int(
            _clamp(_as_number(self.log_rate_limit_per_minute, 120), 1, 100_000)
        )
        self.log_clear_rate_limit_per_minute = int(
            _clamp(_as_number(self.log_clear_rate_limit_per_minute, 30), 1, 100_000)
        )
        self.log_max_entries = int(
            _clamp(_as_number(self.log_max_entries, 1000), 10, 100_000)
        )
        self.log_level = str(self.log_level or "INFO").upper()
        if not isinstance(self.user_agent, str) or len(self.user_agent.strip()) < 20:
            # A short/blank UA ("Mozilla/5.0") is a well-known bot signature and
            # is one of the reasons sites reply with 406/503.
            self.user_agent = DEFAULT_USER_AGENT
        self.user_agent = self.user_agent.strip()
        if isinstance(self.cors_origins, list):
            self.cors_origins = tuple(str(o).strip() for o in self.cors_origins if str(o).strip())
        if not isinstance(self.platforms, dict):
            self.platforms = {name: True for name in PLATFORM_NAMES}
        self.platforms = {
            name: _as_bool(self.platforms.get(name, True), True)
            for name in PLATFORM_NAMES
        }

    @classmethod
    def from_env(cls, config_path: str | Path | None = None) -> "ScoutConfig":
        # .env support: previously python-dotenv was a declared dependency but
        # never invoked, so the documented .env file was silently ignored.
        try:
            from dotenv import load_dotenv

            load_dotenv(override=False)
        except Exception:  # missing package or unreadable file: not fatal
            pass

        cfg = cls()
        # 1) optional config.json
        path = Path(config_path) if config_path else Path("config.json")
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("config.json must contain a JSON object")
                flask = data.get("flask", {}) or {}
                scraper = data.get("scraper", {}) or {}
                pricing = data.get("pricing", {}) or {}
                api = data.get("api", {}) or {}
                platforms = data.get("platforms", {}) or {}

                cfg.host = str(flask.get("host", cfg.host))
                cfg.port = _as_number(flask.get("port", cfg.port), cfg.port)
                cfg.debug = _as_bool(flask.get("debug", cfg.debug), cfg.debug)

                cfg.timeout = _as_number(scraper.get("timeout", cfg.timeout), cfg.timeout)
                cfg.max_retries = _as_number(
                    scraper.get("max_retries", cfg.max_retries), cfg.max_retries
                )
                cfg.retry_backoff = _as_number(
                    scraper.get("retry_backoff", cfg.retry_backoff), cfg.retry_backoff
                )
                # ``rate_limit`` is the historical JSON key for the delay between
                # platform requests; it used to be silently ignored.
                cfg.rate_limit_delay = _as_number(
                    scraper.get("rate_limit", cfg.rate_limit_delay), cfg.rate_limit_delay
                )
                cfg.scrape_deadline = _as_number(
                    scraper.get("deadline", cfg.scrape_deadline), cfg.scrape_deadline
                )
                if "user_agent" in scraper:
                    cfg.user_agent = str(scraper["user_agent"])

                cfg.trim_percent = _as_number(
                    pricing.get("trim_percent", cfg.trim_percent), cfg.trim_percent
                )
                cfg.min_price_threshold = _as_number(
                    pricing.get("min_price_threshold", cfg.min_price_threshold),
                    cfg.min_price_threshold,
                )

                cfg.api_rate_limit_per_minute = _as_number(
                    api.get("rate_limit_per_minute", cfg.api_rate_limit_per_minute),
                    cfg.api_rate_limit_per_minute,
                )
                cfg.log_rate_limit_per_minute = _as_number(
                    api.get("log_rate_limit_per_minute", cfg.log_rate_limit_per_minute),
                    cfg.log_rate_limit_per_minute,
                )
                cfg.max_results = _as_number(
                    api.get("max_results", cfg.max_results), cfg.max_results
                )
                cfg.cors_origins = api.get("cors_origins", cfg.cors_origins) or ()

                if isinstance(platforms, dict):
                    parsed = {}
                    for key, val in platforms.items():
                        clean = str(key).replace("_enabled", "")
                        if clean in PLATFORM_NAMES:
                            parsed[clean] = _as_bool(val, True)
                        else:
                            _module_log.warning(
                                "Unknown platform key in config.json: %r", key
                            )
                    if parsed:
                        cfg.platforms.update(parsed)
            except Exception as exc:  # broken config.json must never prevent startup
                _module_log.warning("Could not read %s: %s", path, exc)

        # 2) environment overrides
        cfg.host = os.getenv("FLASK_HOST", cfg.host)
        cfg.port = _env_int("FLASK_PORT", int(cfg.port))
        cfg.debug = _env_bool("FLASK_DEBUG", cfg.debug)
        cfg.timeout = _env_float("SCRAPER_TIMEOUT", cfg.timeout)
        cfg.max_retries = _env_int("SCRAPER_MAX_RETRIES", int(cfg.max_retries))
        cfg.retry_backoff = _env_float("SCRAPER_RETRY_BACKOFF", cfg.retry_backoff)
        cfg.rate_limit_delay = _env_float("SCRAPER_RATE_LIMIT", cfg.rate_limit_delay)
        cfg.scrape_deadline = _env_float("SCRAPER_DEADLINE", cfg.scrape_deadline)
        cfg.user_agent = os.getenv("SCRAPER_USER_AGENT", cfg.user_agent)
        cfg.api_rate_limit_per_minute = _env_int(
            "API_RATE_LIMIT_PER_MINUTE", int(cfg.api_rate_limit_per_minute)
        )
        cfg.log_rate_limit_per_minute = _env_int(
            "API_LOG_RATE_LIMIT_PER_MINUTE", int(cfg.log_rate_limit_per_minute)
        )
        cfg.log_clear_rate_limit_per_minute = _env_int(
            "API_LOG_CLEAR_RATE_LIMIT_PER_MINUTE",
            int(cfg.log_clear_rate_limit_per_minute),
        )
        cfg.max_results = _env_int("API_MAX_RESULTS", int(cfg.max_results))
        cfg.log_max_entries = _env_int("LOG_MAX_ENTRIES", int(cfg.log_max_entries))
        cfg.ratelimit_storage_uri = os.getenv(
            "RATELIMIT_STORAGE_URI", cfg.ratelimit_storage_uri
        )
        cfg.log_level = os.getenv("LOG_LEVEL", cfg.log_level).upper()
        cfg.warmup_cookies = _env_bool("SCRAPER_WARMUP", cfg.warmup_cookies)
        cfg.use_curl_cffi = _env_bool("SCRAPER_USE_CURL_CFFI", cfg.use_curl_cffi)
        cfg.cors_origins = tuple(
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", ",".join(cfg.cors_origins)).split(",")
            if origin.strip()
        )

        cfg.normalize()
        return cfg
