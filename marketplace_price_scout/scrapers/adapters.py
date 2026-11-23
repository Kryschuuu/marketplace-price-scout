"""Scraper adapters for all marketplaces.

Each adapter returns a list of dicts::

    {
        "platform": str,
        "title": str,
        "price": float,
        "url": str
    }

Failures are **not** swallowed into empty lists: adapters raise
:class:`ScraperError` so the caller can distinguish "the marketplace had no
matching offers" from "the marketplace blocked/failed us". That distinction is
what makes correct HTTP status codes possible.
"""
from __future__ import annotations

import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Callable, Iterable
from urllib.parse import quote_plus, urljoin, urlparse

import cloudscraper
import requests
from bs4 import BeautifulSoup

from marketplace_price_scout.config import PLATFORM_NAMES, RESULT_PLATFORMS, ScoutConfig

# Status codes that usually mean "bot wall / temporary upstream problem" and are
# worth a retry with backoff. 406 (Vinted) and 503 (Amazon) are the two that the
# production log was full of.
RETRYABLE_STATUS = frozenset({403, 406, 408, 425, 429, 500, 502, 503, 504})

# Human readable names used in API responses / warnings.
PLATFORM_LABELS = {
    "kleinanzeigen": "Kleinanzeigen",
    "ebay": "eBay",
    "vinted": "Vinted",
    "mydealz": "mydealz",
    "amazon": "Amazon",
    "hardwareschotte": "Hardwareschotte",
}

COMMON_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ScraperError(Exception):
    """Base class for outbound scraping failures."""

    def __init__(
        self,
        platform: str,
        message: str,
        status_code: int | None = None,
        retry_after: int | None = None,
    ):
        super().__init__(f"{platform}: {message}")
        self.platform = platform
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after


class PlatformTimeout(ScraperError):
    """The marketplace did not answer in time."""


class PlatformBlocked(ScraperError):
    """The marketplace answered with an anti-bot / rate-limit response."""


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


_SESSION_LOCK = threading.Lock()
_SESSIONS: dict[str, tuple[object, int]] = {}


def _warm_up(session, platform: str, config: ScoutConfig, logger=None) -> None:
    """Best-effort homepage visit so the session carries valid cookies.

    Many marketplaces (Vinted in particular) answer 406 when the first request
    already carries a search query but no cookies.
    """
    homepages = {
        "kleinanzeigen": "https://www.kleinanzeigen.de/",
        "ebay": "https://www.ebay.de/",
        "vinted": "https://www.vinted.de/",
        "mydealz": "https://www.mydealz.de/",
        "amazon": "https://www.amazon.de/",
        "hardwareschotte": "https://www.hardwareschotte.de/",
    }
    url = homepages.get(platform)
    if not url:
        return
    try:
        session.get(url, timeout=min(5.0, config.timeout), allow_redirects=True)
    except Exception:
        # Warm-up is an optimisation; never let it break a scrape.
        if logger:
            logger.debug("Warm-up for %s failed", platform, exc_info=True)


def get_scraper(config: ScoutConfig, platform: str | None = None, logger=None):
    """Return a cached HTTP client tuned for the given marketplace.

    Reusing one session per platform keeps cookies (and the TLS fingerprint)
    alive between searches, and the optional warm-up visit avoids the
    "first request is already blocked" pattern.
    
    Order of preference: ``curl_cffi`` (browser TLS impersonation, best ratio
    against bot walls such as Vinted's 406) -> ``cloudscraper`` (Cloudflare
    JS challenge) -> plain ``requests`` session carrying the same headers.
    """
    key = platform or "_default"
    with _SESSION_LOCK:
        cached = _SESSIONS.get(key)
        if cached and cached[1] == id(config):
            return cached[0]

    session = None
    if config.use_curl_cffi:
        try:
            from curl_cffi import requests as curl_req

            session = curl_req.Session(impersonate="chrome120")
        except Exception:  # ImportError or unsupported impersonate target
            session = None

    if session is None:
        try:
            session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
        except Exception:
            session = requests.Session()

    try:
        session.headers.update(COMMON_HEADERS)
        session.headers["User-Agent"] = config.user_agent
    except Exception:
        pass

    if config.warmup_cookies and platform:
        _warm_up(session, platform, config, logger)

    with _SESSION_LOCK:
        _SESSIONS[key] = (session, id(config))
    return session


def reset_sessions() -> None:
    """Drop cached HTTP sessions (used by tests and after config reloads)."""
    with _SESSION_LOCK:
        for session, _ in _SESSIONS.values():
            close = getattr(session, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        _SESSIONS.clear()


_MONEY_RE = re.compile(r"\d[\d.,]*")


def clean_price(price_str: str) -> float:
    """Extract a numeric price from a marketplace string.

    Handles German (``1.299,99 €``), US (``1,299.99``), plain (``99 €``) and
    trailing-dash (``99,-``) formats, plus price ranges (``10 - 20 €``, the
    first amount wins). Returns ``0.0`` when no price can be parsed.
    """
    if not price_str:
        return 0.0
    if not isinstance(price_str, str):
        price_str = str(price_str)

    text = (
        price_str.replace("€", " ")
        .replace("EUR", " ")
        .replace("VB", " ")
        .replace("Preis auf Anfrage", " ")
        .replace("\u00a0", " ")
        .replace("\u202f", " ")
    )

    match = _MONEY_RE.search(text)
    if not match:
        return 0.0

    token = match.group(0).rstrip(".,")
    has_dot, has_comma = "." in token, "," in token

    if has_dot and has_comma:
        # The right-most separator is the decimal separator.
        decimal = "." if token.rfind(".") > token.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        token = token.replace(thousands, "").replace(decimal, ".")
    elif has_comma:
        # "1,299" is a thousands grouping, "1,29" is a decimal value.
        if token.count(",") > 1 or len(token.split(",")[-1]) == 3:
            token = token.replace(",", "")
        else:
            token = token.replace(",", ".")
    elif has_dot:
        if token.count(".") > 1 or len(token.split(".")[-1]) == 3:
            token = token.replace(".", "")

    try:
        value = float(token)
    except ValueError:
        return 0.0
    if value != value or value in (float("inf"), float("-inf")):
        return 0.0
    return value


def is_valid_item(
    title: str, price: float, min_price: float, max_price: float, blacklist: Iterable[str]
) -> bool:
    """Check if an item meets all criteria."""
    if not isinstance(title, str) or not title.strip():
        return False
    if price is None or price <= 0:
        return False

    title_lower = title.lower()
    for word in blacklist:
        word = str(word).strip().lower()
        if word and word in title_lower:
            return False

    return min_price <= price <= max_price


def _is_safe_link(link: str, allowed_hosts: Iterable[str]) -> bool:
    """Reject non-HTTPS and off-site links (open-redirect / SSRF hygiene)."""
    parsed = urlparse(link)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return any(host == allowed or host.endswith("." + allowed) for allowed in allowed_hosts)


def _backoff_delay(config: ScoutConfig, attempt: int) -> float:
    """Exponential backoff with jitter, capped so a request stays bounded."""
    base = config.retry_backoff * (2**attempt)
    return min(base, 8.0) * (0.75 + random.random() * 0.5)


def fetch(
    url: str,
    scraper,
    config: ScoutConfig,
    platform: str,
    logger,
    *,
    timeout: float | None = None,
    referer: str | None = None,
):
    """GET ``url`` with retries, backoff and clear platform-scoped errors.

    Raises :class:`PlatformTimeout` / :class:`PlatformBlocked` /
    :class:`ScraperError` instead of returning a body-less response, so callers
    can map the failure to a meaningful HTTP status.
    """
    request_timeout = min(config.timeout, timeout) if timeout else config.timeout
    request_timeout = max(1.0, request_timeout)
    last_error: ScraperError | None = None

    for attempt in range(config.max_retries + 1):
        headers = {"Referer": referer} if referer else {}
        try:
            response = scraper.get(
                url, timeout=request_timeout, headers=headers, allow_redirects=True
            )
        except (requests.Timeout, TimeoutError) as exc:  # requests/urllib3 timeouts
            last_error = PlatformTimeout(platform, f"timeout after {request_timeout:.0f}s")
            logger.warning("%s timeout for %s (attempt %s)", platform, url, attempt + 1)
            if attempt >= config.max_retries:
                raise last_error from exc
        except Exception as exc:
            # curl_cffi has its own exception hierarchy; classify by class name.
            is_timeout = "timeout" in exc.__class__.__name__.lower()
            last_error = (
                PlatformTimeout(platform, f"timeout after {request_timeout:.0f}s")
                if is_timeout
                else ScraperError(platform, f"request failed: {exc.__class__.__name__}")
            )
            logger.warning(
                "%s request error for %s (attempt %s): %s",
                platform,
                url,
                attempt + 1,
                exc,
            )
            if attempt >= config.max_retries:
                raise last_error from exc
        else:
            status = getattr(response, "status_code", 0)
            if status == 200:
                return response
            if status in (301, 302, 303, 307, 308):
                # allow_redirects normally handles this; a redirect loop is fatal.
                last_error = ScraperError(platform, f"redirect loop (HTTP {status})", status)
                raise last_error
            if status in (401, 403, 406, 429):
                last_error = PlatformBlocked(
                    platform,
                    f"blocked (HTTP {status})",
                    status,
                    retry_after=_parse_retry_after(response),
                )
            else:
                last_error = ScraperError(platform, f"HTTP {status}", status)

            logger.info("%s returned HTTP %s (attempt %s)", platform, status, attempt + 1)
            if status not in RETRYABLE_STATUS or attempt >= config.max_retries:
                raise last_error

        delay = _backoff_delay(config, attempt)
        retry_after = getattr(last_error, "retry_after", None)
        if retry_after:
            delay = min(max(delay, float(retry_after)), 10.0)
        logger.info("%s retrying in %.1fs", platform, delay)
        time.sleep(delay)

    raise last_error or ScraperError(platform, "unknown error")


def _parse_retry_after(response) -> int | None:
    raw = None
    try:
        raw = response.headers.get("Retry-After")
    except Exception:
        return None
    if not raw:
        return None
    try:
        return max(0, min(int(str(raw).strip()), 30))
    except (TypeError, ValueError):
        return None


def _scrape_cards(
    query: str,
    min_price: float,
    max_price: float,
    blacklist: list[str],
    scraper,
    platform: str,
    url: str,
    selectors: dict,
    base: str,
    config: ScoutConfig,
    logger,
    *,
    timeout: float | None = None,
) -> list[dict]:
    """Parse a site's public search-result cards; tolerate markup changes."""
    response = fetch(
        url, scraper, config, platform, logger, timeout=timeout, referer=base + "/"
    )

    try:
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as exc:  # malformed body is an upstream error, not "no results"
        raise ScraperError(platform, f"unparseable response: {exc}") from exc

    base_host = urlparse(base).hostname or ""
    allowed_hosts = {base_host, base_host.removeprefix("www.")}

    results: list[dict] = []
    for card in soup.select(selectors["card"])[: config.max_results]:
        try:
            title_el = card.select_one(selectors["title"])
            price_el = card.select_one(selectors["price"])
            link_el = card.select_one(selectors["link"])
            if not (title_el and price_el and link_el):
                continue
            title = title_el.get_text(" ", strip=True)
            price = clean_price(price_el.get_text(" ", strip=True))
            link = urljoin(base, link_el.get("href", ""))
            if not _is_safe_link(link, allowed_hosts):
                continue
            if is_valid_item(title, price, min_price, max_price, blacklist):
                results.append(
                    {"platform": platform, "title": title[:100], "price": price, "url": link}
                )
        except Exception:
            logger.debug("%s: could not parse a result card", platform, exc_info=True)

    if not results:
        # A page with no parsable cards is frequently a challenge/consent page
        # rather than a genuinely empty result list. Distinguish it so the API
        # can report "unclear" instead of claiming "no offers exist".
        if soup.select_one("form[action*='challenge'], #challenge-form, .cf-browser-verification"):
            raise PlatformBlocked(platform, "bot challenge page returned", 200)
    return results


# ---------------------------------------------------------------------------
# Platform adapters
# ---------------------------------------------------------------------------


def scrape_kleinanzeigen(
    query: str,
    min_price: float,
    max_price: float,
    blacklist: list[str],
    scraper,
    config: ScoutConfig,
    logger,
    *,
    timeout: float | None = None,
) -> list[dict]:
    """Scrape Kleinanzeigen marketplace."""
    base = "https://www.kleinanzeigen.de"
    url = (
        f"{base}/s-suchanfrage.html?keywords={quote_plus(query)}"
        f"&minPrice={min_price:g}&maxPrice={max_price:g}"
    )
    response = fetch(
        url, scraper, config, "Kleinanzeigen", logger, timeout=timeout, referer=base + "/"
    )
    soup = BeautifulSoup(response.text, "html.parser")

    items: list[dict] = []
    for ad in soup.select("article.aditem")[: config.max_results]:
        try:
            title_elem = ad.select_one("a.ellipsis") or ad.select_one("h2 a")
            price_elem = ad.select_one(
                "p.aditem-main--middle--price-shipping--price"
            ) or ad.select_one(".aditem-main--middle--price")
            if not (title_elem and price_elem):
                continue
            title = title_elem.get_text(" ", strip=True)
            price = clean_price(price_elem.get_text(" ", strip=True))
            link = urljoin(base, title_elem.get("href", ""))
            if not _is_safe_link(link, {"www.kleinanzeigen.de", "kleinanzeigen.de"}):
                continue
            if is_valid_item(title, price, min_price, max_price, blacklist):
                items.append(
                    {"platform": "Kleinanzeigen", "title": title[:100], "price": price, "url": link}
                )
        except Exception:
            logger.debug("Error parsing Kleinanzeigen item", exc_info=True)
    return items


def scrape_ebay(
    query: str,
    min_price: float,
    max_price: float,
    blacklist: list[str],
    scraper,
    config: ScoutConfig,
    logger,
    *,
    timeout: float | None = None,
) -> list[dict]:
    """Scrape eBay marketplace."""
    base = "https://www.ebay.de"
    url = (
        f"{base}/sch/i.html?_nkw={quote_plus(query)}&_sacat=0"
        f"&LH_ItemCondition=3000%7C1000&_ipg=60"
    )
    response = fetch(
        url, scraper, config, "eBay", logger, timeout=timeout, referer=base + "/"
    )
    soup = BeautifulSoup(response.text, "html.parser")

    items: list[dict] = []
    for entry in soup.select("li.s-item, div.s-item__info")[: config.max_results]:
        try:
            title_elem = entry.select_one(".s-item__title")
            price_elem = entry.select_one(".s-item__price")
            link_elem = entry.select_one("a.s-item__link")
            if not (title_elem and price_elem and link_elem):
                continue
            title = title_elem.get_text(" ", strip=True).replace("Neues Angebot", "").strip()
            price = clean_price(price_elem.get_text(" ", strip=True))
            link = urljoin(base, link_elem.get("href", "").split("?")[0])
            if not _is_safe_link(link, {"www.ebay.de", "ebay.de"}):
                continue
            if "Shop-Artikel" in title:
                continue
            if is_valid_item(title, price, min_price, max_price, blacklist):
                items.append(
                    {"platform": "eBay", "title": title[:100], "price": price, "url": link}
                )
        except Exception:
            logger.debug("Error parsing eBay item", exc_info=True)
    return items


def scrape_vinted(
    query: str,
    min_price: float,
    max_price: float,
    blacklist: list[str],
    scraper,
    config: ScoutConfig,
    logger,
    *,
    timeout: float | None = None,
) -> list[dict]:
    """Scrape Vinted marketplace (frequently answers 406 to plain requests)."""
    return _scrape_cards(
        query,
        min_price,
        max_price,
        blacklist,
        scraper,
        "Vinted",
        "https://www.vinted.de/catalog?search_text=" + quote_plus(query),
        {
            "card": ".new-item-box__container, .feed-grid__item",
            "title": "a[href]",
            "price": ".price, .new-price",
            "link": "a[href]",
        },
        "https://www.vinted.de",
        config,
        logger,
        timeout=timeout,
    )


def scrape_mydealz(
    query: str,
    min_price: float,
    max_price: float,
    blacklist: list[str],
    scraper,
    config: ScoutConfig,
    logger,
    *,
    timeout: float | None = None,
) -> list[dict]:
    """Scrape mydealz marketplace."""
    return _scrape_cards(
        query,
        min_price,
        max_price,
        blacklist,
        scraper,
        "mydealz",
        "https://www.mydealz.de/search?q=" + quote_plus(query),
        {
            "card": "article, .thread",
            "title": "a.thread-link, h2 a",
            "price": ".thread-price, .price",
            "link": "a.thread-link, h2 a",
        },
        "https://www.mydealz.de",
        config,
        logger,
        timeout=timeout,
    )


def scrape_amazon(
    query: str,
    min_price: float,
    max_price: float,
    blacklist: list[str],
    scraper,
    config: ScoutConfig,
    logger,
    *,
    timeout: float | None = None,
) -> list[dict]:
    """Scrape Amazon marketplace."""
    return _scrape_cards(
        query,
        min_price,
        max_price,
        blacklist,
        scraper,
        "Amazon",
        "https://www.amazon.de/s?k=" + quote_plus(query),
        {
            "card": "div[data-component-type='s-search-result']",
            "title": "h2 a span, h2 span",
            "price": ".a-price .a-offscreen, .a-price",
            "link": "h2 a, a.a-link-normal",
        },
        "https://www.amazon.de",
        config,
        logger,
        timeout=timeout,
    )


ADAPTERS: dict[str, Callable[..., list[dict]]] = {
    "kleinanzeigen": scrape_kleinanzeigen,
    "ebay": scrape_ebay,
    "vinted": scrape_vinted,
    "mydealz": scrape_mydealz,
    "amazon": scrape_amazon,
}


def get_hardwareschotte_index(
    query: str,
    scraper,
    config: ScoutConfig,
    logger,
    *,
    timeout: float | None = None,
) -> float | None:
    """Fetch reference price from Hardwareschotte."""
    if scraper is None:
        scraper = get_scraper(config, "hardwareschotte", logger)
    url = "https://www.hardwareschotte.de/suche/?searchstring=" + quote_plus(query)
    try:
        response = fetch(
            url,
            scraper,
            config,
            "Hardwareschotte",
            logger,
            timeout=timeout,
            referer="https://www.hardwareschotte.de/",
        )
    except ScraperError as exc:
        # A missing reference price must never fail the whole request.
        logger.warning("Hardwareschotte reference price unavailable: %s", exc.message)
        return None

    soup = BeautifulSoup(getattr(response, "text", "") or "", "html.parser")
    prices = [
        clean_price(node.get_text(" ", strip=True))
        for node in soup.select(".articlePrice, .price")
    ]
    prices = [p for p in prices if p > config.min_price_threshold]
    return min(prices) if prices else None


def calculate_trimmed_mean(
    items: list[dict],
    trim_percent: float | None = None,
    config: ScoutConfig | None = None,
) -> float:
    """Calculate trimmed mean price (removes outliers)."""
    if trim_percent is None:
        trim_percent = config.trim_percent if config else 0.15
    trim_percent = max(0.0, min(0.49, float(trim_percent)))

    prices = sorted(
        float(item.get("price", 0) or 0) for item in items if item.get("price")
    )
    prices = [price for price in prices if price > 0]
    if not prices:
        return 0.0
    if len(prices) < 4:
        return sum(prices) / len(prices)

    trim_count = int(len(prices) * trim_percent)
    trimmed = prices[trim_count : len(prices) - trim_count] if trim_count else prices
    return sum(trimmed) / len(trimmed) if trimmed else 0.0


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class PlatformOutcome:
    """Result of one platform scrape attempt."""

    platform: str
    ok: bool
    result_count: int = 0
    status_code: int | None = None
    error: str | None = None
    skipped: bool = False
    timed_out: bool = False
    duration: float = 0.0

    def as_dict(self) -> dict:
        return {
            "platform": PLATFORM_LABELS.get(self.platform, self.platform),
            "ok": self.ok,
            "resultCount": self.result_count,
            "httpStatus": self.status_code,
            "error": self.error,
            "skipped": self.skipped,
            "timedOut": self.timed_out,
            "durationMs": int(self.duration * 1000),
        }


@dataclass
class ScrapeReport:
    """Aggregated result of a multi-platform scrape."""

    items: list[dict] = field(default_factory=list)
    outcomes: list[PlatformOutcome] = field(default_factory=list)
    duration: float = 0.0
    deadline_exceeded: bool = False

    @property
    def attempted(self) -> list[PlatformOutcome]:
        return [o for o in self.outcomes if not o.skipped]

    @property
    def failed(self) -> list[PlatformOutcome]:
        return [o for o in self.attempted if not o.ok]

    @property
    def succeeded(self) -> list[PlatformOutcome]:
        return [o for o in self.attempted if o.ok]

    @property
    def all_failed(self) -> bool:
        """True when every attempted platform errored out."""
        return bool(self.attempted) and not self.succeeded

    @property
    def warnings(self) -> list[str]:
        return [
            f"{PLATFORM_LABELS.get(o.platform, o.platform)}: {o.error}"
            for o in self.failed
            if o.error
        ]


def _run_platform(
    platform: str,
    query: str,
    min_price: float,
    max_price: float,
    blacklist: list[str],
    config: ScoutConfig,
    logger,
    timeout: float,
) -> tuple[list[dict], PlatformOutcome]:
    started = time.monotonic()
    try:
        scraper = get_scraper(config, platform, logger)
        items = ADAPTERS[platform](
            query,
            min_price,
            max_price,
            blacklist,
            scraper,
            config,
            logger,
            timeout=timeout,
        )
        return items, PlatformOutcome(
            platform=platform,
            ok=True,
            result_count=len(items),
            duration=time.monotonic() - started,
        )
    except ScraperError as exc:
        logger.warning("%s failed: %s", platform, exc.message)
        return [], PlatformOutcome(
            platform=platform,
            ok=False,
            status_code=exc.status_code,
            error=exc.message,
            timed_out=isinstance(exc, PlatformTimeout),
            duration=time.monotonic() - started,
        )
    except Exception as exc:  # adapter bug must not kill the whole request
        logger.exception("%s scraping error", platform)
        return [], PlatformOutcome(
            platform=platform,
            ok=False,
            error=f"internal scraper error ({exc.__class__.__name__})",
            duration=time.monotonic() - started,
        )


def resolve_platforms(
    config: ScoutConfig, selection: dict[str, bool] | None = None
) -> dict[str, bool]:
    """Merge the per-request selection with the configured defaults.

    A platform must be enabled *both* in the configuration and in the request
    to be scraped. Omitting ``selection`` keeps the configured defaults.
    """
    resolved = dict(config.platforms)
    for name, enabled in (selection or {}).items():
        if name in resolved:
            resolved[name] = bool(enabled) and bool(config.platforms.get(name, True))
    return resolved


def scrape_all_platforms(
    query: str,
    min_price: float,
    max_price: float,
    blacklist: list[str],
    config: ScoutConfig,
    logger,
    selection: dict[str, bool] | None = None,
) -> ScrapeReport:
    """Scrape all enabled result platforms in parallel, bounded by a deadline.

    Only platforms that are enabled in the configuration *and* selected in the
    request are contacted — the previous implementation ignored the selection
    and always hit Amazon and Vinted (hence the 503/406 noise in the logs).
    """
    resolved = resolve_platforms(config, selection)
    active = [name for name in RESULT_PLATFORMS if resolved.get(name)]

    report = ScrapeReport()
    # Report every disabled platform (including hardwareschotte) so the client
    # can show what was intentionally not consulted.
    skipped = [name for name in PLATFORM_NAMES if not resolved.get(name)]
    report.outcomes.extend(
        PlatformOutcome(platform=name, ok=True, skipped=True) for name in skipped
    )
    if skipped:
        logger.info("Skipping disabled platforms: %s", ", ".join(skipped))
    if not active:
        logger.info("No result platform enabled for query: %s", query)
        return report

    logger.info("Scraping %s in parallel", ", ".join(active))
    started = time.monotonic()
    deadline = config.scrape_deadline
    per_platform_timeout = min(config.timeout, deadline)

    executor = ThreadPoolExecutor(
        max_workers=min(len(active), 6), thread_name_prefix="scrape"
    )
    futures = {
        executor.submit(
            _run_platform,
            name,
            query,
            min_price,
            max_price,
            blacklist,
            config,
            logger,
            per_platform_timeout,
        ): name
        for name in active
    }
    done, pending = wait(futures, timeout=deadline)

    for future in done:
        name = futures[future]
        try:
            items, outcome = future.result()
        except Exception:  # defensive: _run_platform already catches everything
            logger.exception("%s scraping error", name)
            report.outcomes.append(
                PlatformOutcome(platform=name, ok=False, error="internal scraper error")
            )
            continue
        report.items.extend(items)
        report.outcomes.append(outcome)

    if pending:
        report.deadline_exceeded = True
        for future in pending:
            name = futures[future]
            future.cancel()
            logger.warning(
                "%s exceeded the %.0fs scrape deadline and was abandoned", name, deadline
            )
            report.outcomes.append(
                PlatformOutcome(
                    platform=name,
                    ok=False,
                    error=f"exceeded {deadline:.0f}s scrape deadline",
                    timed_out=True,
                )
            )

    # Do not block the response on abandoned threads; they carry their own
    # request timeouts and are therefore bounded.
    executor.shutdown(wait=False, cancel_futures=True)

    report.duration = time.monotonic() - started
    logger.info(
        "Scrape finished in %.2fs: %s result(s), %s platform(s) ok, %s failed",
        report.duration,
        len(report.items),
        len(report.succeeded),
        len(report.failed),
    )
    return report
