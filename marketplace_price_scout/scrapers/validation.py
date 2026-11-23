"""Validation and normalization helpers."""
from __future__ import annotations

import math


def validate_input(query: str, min_price: float, max_price: float, blacklist: list | str) -> tuple[str, float, float, list[str]]:
    """Validate and sanitize user input."""
    if not query or len(query.strip()) == 0:
        raise ValueError("Search query cannot be empty")
    if len(query) > 200:
        raise ValueError("Search query too long (max 200 characters)")
    if not math.isfinite(float(min_price)) or not math.isfinite(float(max_price)):
        raise ValueError("Prices must be finite numbers")
    
    if isinstance(blacklist, str):
        blacklist = [x.strip() for x in blacklist.split(",")]
    if not isinstance(blacklist, list):
        raise ValueError("Blacklist must be a list")
    
    if min_price < 0 or max_price < 0:
        raise ValueError("Prices cannot be negative")
    if min_price > max_price:
        raise ValueError("Min price cannot exceed max price")
    if len(blacklist) > 50:
        raise ValueError("Too many blacklist items (max 50)")
    
    return (
        query.strip()[:200],
        float(min_price),
        float(max_price),
        [item.strip()[:50] for item in blacklist if item.strip()][:50]
    )
