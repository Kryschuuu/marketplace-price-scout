"""Scraper adapters for all marketplaces.

Each adapter returns a list of dicts:
{
    "platform": str,
    "title": str,
    "price": float,
    "url": str
}
"""
from __future__ import annotations

import math
import time
from urllib.parse import quote_plus, urljoin, urlparse

import cloudscraper
import requests
from bs4 import BeautifulSoup

from marketplace_price_scout.config import ScoutConfig

# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def get_scraper(config: ScoutConfig):
    """Return a scraper/session instance.

    Uses curl_cffi if available (best bypass); falls back to cloudscraper;
    finally falls back to requests.Session.
    """
    # 1. Try curl_cffi
    try:
        if config.use_curl_cffi:
            from curl_cffi import requests as curl_req

            session = curl_req.Session(impersonate="chrome110")
            session.timeout = config.timeout
            return session
    except ImportError:
        pass

    # 2. Try cloudscraper
    try:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "desktop": True}
        )
        scraper.timeout = config.timeout
        return scraper
    except Exception:
        pass

    # 3. Fallback to requests
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )
    session.timeout = config.timeout
    return session


def clean_price(price_str: str) -> float:
    """Extract numeric price from string with error handling."""
    if not price_str:
        return 0.0
    try:
        cleaned = (
            price_str.replace("€", "")
            .replace("VB", "")
            .replace("Preis auf Anfrage", "0")
            .replace(".", "")
            .replace(",", ".")
            .strip()
        )
        filtered = "".join([c for c in cleaned if c.isdigit() or c == "."])
        return float(filtered) if filtered else 0.0
    except Exception:
        return 0.0


def is_valid_item(title: str, price: float, min_price: float, max_price: float, blacklist: list[str]) -> bool:
    """Check if an item meets all criteria."""
    if not title or price is None:
        return False

    title_lower = title.lower()
    for word in blacklist:
        word = word.strip().lower()
        if word and word in title_lower:
            return False

    if price < min_price or price > max_price:
        return False

    return True


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
) -> list[dict]:
    """Parse a site's public search-result cards; tolerate markup changes."""
    results = []
    try:
        response = scraper.get(url, timeout=config.timeout)
        if response.status_code != 200:
            logger.info("%s returned HTTP %s", platform, response.status_code)
            return results
        soup = BeautifulSoup(response.text, "html.parser")
        for card in soup.select(selectors["card"])[: config.max_results]:
            title_el = card.select_one(selectors["title"])
            price_el = card.select_one(selectors["price"])
            link_el = card.select_one(selectors["link"])
            if not (title_el and price_el and link_el):
                continue
            title = title_el.get_text(" ", strip=True)
            price = clean_price(price_el.get_text(" ", strip=True))
            link = urljoin(base, link_el.get("href", ""))
            if urlparse(link).scheme != "https" or urlparse(link).hostname not in (
                urlparse(base).hostname,
            ):
                continue
            if is_valid_item(title, price, min_price, max_price, blacklist):
                results.append(
                    {"platform": platform, "title": title[:100], "price": price, "url": link}
                )
    except requests.Timeout:
        logger.warning("%s timeout for query: %s", platform, query)
    except Exception:
        logger.exception("%s scraping error", platform)
    return results


# ---------------------------------------------------------------------------
# Platform adapters
# ---------------------------------------------------------------------------


def scrape_kleinanzeigen(query: str, min_price: float, max_price: float, blacklist: list[str], scraper, config: ScoutConfig, logger) -> list[dict]:
    """Scrape Kleinanzeigen marketplace."""
    items = []
    try:
        formatted_query = quote_plus(query).replace("+", "-")
        url = f"https://www.kleinanzeigen.de/s-{formatted_query}/k0"
        response = scraper.get(url, timeout=config.timeout)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            ads = soup.select("article.aditem")[: config.max_results]
            for ad in ads:
                try:
                    title_elem = ad.select_one("a.ellipsis") or ad.select_one("h2 a")
                    price_elem = ad.select_one("p.aditem-main--middle--price-shipping--price")
                    if title_elem and price_elem:
                        title = title_elem.get_text(strip=True)
                        price = clean_price(price_elem.get_text())
                        if is_valid_item(title, price, min_price, max_price, blacklist):
                            link = urljoin("https://www.kleinanzeigen.de", title_elem.get("href", ""))
                            if urlparse(link).netloc != "www.kleinanzeigen.de":
                                continue
                            items.append(
                                {
                                    "platform": "Kleinanzeigen",
                                    "title": title[:100],
                                    "price": price,
                                    "url": link,
                                }
                            )
                except Exception:
                    logger.debug("Error parsing Kleinanzeigen item", exc_info=True)
    except requests.Timeout:
        logger.warning("Kleinanzeigen timeout for query: %s", query)
    except Exception:
        logger.exception("Kleinanzeigen scraping error")
    return items


def scrape_ebay(query: str, min_price: float, max_price: float, blacklist: list[str], scraper, config: ScoutConfig, logger) -> list[dict]:
    """Scrape eBay marketplace."""
    items = []
    try:
        formatted_query = quote_plus(query)
        url = f"https://www.ebay.de/sch/i.html?_nkw={formatted_query}&_sacat=0&LH_ItemCondition=3000|1000"
        response = scraper.get(url, timeout=config.timeout)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            ebay_items = soup.select("div.s-item__info")[: config.max_results]
            for item in ebay_items:
                try:
                    title_elem = item.select_one(".s-item__title")
                    price_elem = item.select_one(".s-item__price")
                    link_elem = item.select_one("a.s-item__link")
                    if title_elem and price_elem and link_elem:
                        title = title_elem.get_text(strip=True).replace("Neues Angebot", "")
                        price = clean_price(price_elem.get_text())
                        if "Shop-Artikel" not in title and is_valid_item(title, price, min_price, max_price, blacklist):
                            url = urljoin("https://www.ebay.de", link_elem.get("href", "#").split("?")[0])
                            if urlparse(url).scheme != "https" or urlparse(url).hostname not in ("www.ebay.de", "ebay.de"):
                                continue
                            items.append(
                                {
                                    "platform": "eBay",
                                    "title": title[:100],
                                    "price": price,
                                    "url": url,
                                }
                            )
                except Exception:
                    logger.debug("Error parsing eBay item", exc_info=True)
    except requests.Timeout:
        logger.warning("eBay timeout for query: %s", query)
    except Exception:
        logger.exception("eBay scraping error")
    return items


def scrape_vinted(query: str, min_price: float, max_price: float, blacklist: list[str], scraper, config: ScoutConfig, logger) -> list[dict]:
    """Scrape Vinted marketplace."""
    return _scrape_cards(
        query,
        min_price,
        max_price,
        blacklist,
        scraper,
        "Vinted",
        "https://www.vinted.de/catalog?search_text=" + quote_plus(query),
        {"card": ".new-item-box__container, .feed-grid__item", "title": "a[href]", "price": ".price, .new-price", "link": "a[href]"},
        "https://www.vinted.de",
        config,
        logger,
    )


def scrape_mydealz(query: str, min_price: float, max_price: float, blacklist: list[str], scraper, config: ScoutConfig, logger) -> list[dict]:
    """Scrape mydealz marketplace."""
    return _scrape_cards(
        query,
        min_price,
        max_price,
        blacklist,
        scraper,
        "mydealz",
        "https://www.mydealz.de/search?q=" + quote_plus(query),
        {"card": "article, .thread", "title": "a.thread-link, h2 a", "price": ".thread-price, .price", "link": "a.thread-link, h2 a"},
        "https://www.mydealz.de",
        config,
        logger,
    )


def scrape_amazon(query: str, min_price: float, max_price: float, blacklist: list[str], scraper, config: ScoutConfig, logger) -> list[dict]:
    """Scrape Amazon marketplace."""
    return _scrape_cards(
        query,
        min_price,
        max_price,
        blacklist,
        scraper,
        "Amazon",
        "https://www.amazon.de/s?k=" + quote_plus(query),
        {"card": "div[data-component-type='s-search-result']", "title": "h2 a span", "price": ".a-price .a-offscreen", "link": "h2 a"},
        "https://www.amazon.de",
        config,
        logger,
    )


def get_hardwareschotte_index(query: str, scraper, config: ScoutConfig, logger) -> float | None:
    """Fetch reference price from Hardwareschotte."""
    try:
        formatted_query = quote_plus(query)
        url = f"https://www.hardwareschotte.de/suche/?searchstring={formatted_query}"
        response = scraper.get(url, timeout=config.timeout)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            prices = [clean_price(p.get_text()) for p in soup.select(".articlePrice, .price")]
            prices = [p for p in prices if p > config.min_price_threshold]
            if prices:
                return min(prices)
    except requests.Timeout:
        logger.warning("Hardwareschotte timeout for query: %s", query)
    except Exception:
        logger.error("Hardwareschotte error", exc_info=True)
    return None


def calculate_trimmed_mean(items: list[dict], trim_percent: float | None = None, config: ScoutConfig | None = None) -> float:
    """Calculate trimmed mean price (removes outliers)."""
    if trim_percent is None and config:
        trim_percent = config.trim_percent
    elif trim_percent is None:
        trim_percent = 0.15

    if not items:
        return 0.0

    prices = sorted([i["price"] for i in items])

    if len(prices) < 4:
        return sum(prices) / len(prices)

    trim_count = int(len(prices) * trim_percent)
    trimmed = prices[trim_count:-trim_count] if trim_count > 0 else prices

    return sum(trimmed) / len(trimmed) if trimmed else 0.0


def scrape_all_platforms(
    query: str,
    min_price: float,
    max_price: float,
    blacklist: list[str],
    config: ScoutConfig,
    logger,
) -> list[dict]:
    """Scrape enabled platforms concurrently."""
    items = []
    
    # Map platform names to functions
    adapters = {
        "kleinanzeigen": scrape_kleinanzeigen,
        "ebay": scrape_ebay,
        "vinted": scrape_vinted,
        "mydealz": scrape_mydealz,
        "amazon": scrape_amazon,
    }

    # Execute enabled adapters
    for platform, enabled in config.platforms.items():
        if not enabled:
            logger.info("Skipping disabled platform: %s", platform)
            continue
        if platform not in adapters:
            continue
        
        scraper = get_scraper(config)
        fn = adapters[platform]
        try:
            res = fn(query, min_price, max_price, blacklist, scraper, config, logger)
            items.extend(res)
            # Respect rate limit delay between platforms
            if config.rate_limit_delay > 0:
                time.sleep(config.rate_limit_delay)
        except Exception:
            logger.exception("Error scraping %s", platform)
            
    return items
