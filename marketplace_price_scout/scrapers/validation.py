"""Validation and normalization helpers.

All user supplied values pass through here before they reach a scraper.
Anything structurally wrong raises :class:`ValueError`, which the API layer
maps to HTTP 400 — it must never surface as a 500 or trigger an outbound
request.
"""
from __future__ import annotations

import math

from marketplace_price_scout.config import PLATFORM_NAMES

MAX_QUERY_LENGTH = 200
MAX_BLACKLIST_ITEMS = 50
MAX_BLACKLIST_WORD_LENGTH = 50
# Upper bound for a single search. Prevents absurd ranges from being forwarded
# to the marketplaces (and from silently returning nothing).
MAX_PRICE = 1_000_000.0


def _as_number(value: object, default: float, label: str) -> float:
    """Convert to float, tolerating numeric strings; reject everything else."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return default
    if isinstance(value, bool) or isinstance(value, (list, tuple, dict, set)):
        raise ValueError(f"{label} must be a number")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number") from None
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def validate_platforms(raw: object) -> dict[str, bool]:
    """Normalize the per-request platform selection.

    ``None``/absent means "use the configured defaults". A dict may contain
    booleans (or truthy/falsy scalars) for any known platform; unknown keys are
    rejected so typos are visible instead of silently ignored.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("platforms must be an object of platform -> boolean")

    selection: dict[str, bool] = {}
    for key, value in raw.items():
        name = str(key).strip().lower()
        if name not in PLATFORM_NAMES:
            raise ValueError(
                f"Unknown platform '{key}'. Valid platforms: {', '.join(PLATFORM_NAMES)}"
            )
        if isinstance(value, str):
            selection[name] = value.strip().lower() in {"1", "true", "yes", "on"}
        elif isinstance(value, (list, tuple, dict, set)):
            raise ValueError(f"Platform '{name}' must be a boolean")
        else:
            selection[name] = bool(value)
    return selection


def validate_input(
    query: object,
    min_price: object,
    max_price: object,
    blacklist: object,
) -> tuple[str, float, float, list[str]]:
    """Validate and sanitize search input."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query cannot be empty")
    query = " ".join(query.split())
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"Search query too long (max {MAX_QUERY_LENGTH} characters)")

    min_price = _as_number(min_price, 0.0, "minPrice")
    max_price = _as_number(max_price, MAX_PRICE, "maxPrice")

    if min_price < 0 or max_price < 0:
        raise ValueError("Prices cannot be negative")
    if min_price > MAX_PRICE or max_price > MAX_PRICE:
        raise ValueError(f"Prices cannot exceed {MAX_PRICE:.0f}")
    if min_price > max_price:
        raise ValueError("Min price cannot exceed max price")

    if blacklist is None:
        blacklist = []
    if isinstance(blacklist, str):
        blacklist = blacklist.split(",")
    if not isinstance(blacklist, (list, tuple)):
        raise ValueError("Blacklist must be a list of strings or a comma separated string")
    if len(blacklist) > MAX_BLACKLIST_ITEMS:
        raise ValueError(f"Too many blacklist items (max {MAX_BLACKLIST_ITEMS})")

    words: list[str] = []
    for item in blacklist:
        if item is None:
            continue
        if not isinstance(item, str):
            raise ValueError("Blacklist entries must be strings")
        word = item.strip()
        if word:
            words.append(word[:MAX_BLACKLIST_WORD_LENGTH])

    return query, float(min_price), float(max_price), words[:MAX_BLACKLIST_ITEMS]
