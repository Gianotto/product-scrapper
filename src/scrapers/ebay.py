"""
eBay HTML scraper.

Fetches an eBay search-results page filtered to Buy It Now listings and parses
product items. Uses a CSS-selector fallback chain to handle minor site layout
changes.

The URL is automatically augmented with ``&LH_BIN=1`` to restrict results to
Buy It Now (not auctions).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed

from src.models import PriceCheck, Product
from src.scrapers.base import BaseScraper

# ---------------------------------------------------------------------------
# CSS selector fallback chains
# ---------------------------------------------------------------------------

_CARD_SELECTORS = [
    ".s-item",
    "[class*='s-item']",
]

_TITLE_SELECTORS = [
    ".s-item__title",
    "h3.s-item__title",
    ".s-item__link",
]

_PRICE_SELECTORS = [
    ".s-item__price",
    ".s-item__detail",
]

_BASE_URL = "https://www.ebay.com"

# Dummy header item title eBay inserts as first result
_DUMMY_TITLE = "shop on ebay"

# Maximum size of the debug HTML dump (1 MB)
_DEBUG_MAX_BYTES = 1 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_price(text: str | None) -> float | None:
    """Parse a price string like '$1,249.99' into a float, or return None."""
    if not text:
        return None
    # Handle price ranges like "$1,000.00 to $1,200.00" — take the lower bound
    parts = re.split(r"\s+to\s+", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^\d.]", "", parts[0].replace(",", ""))
    try:
        return float(cleaned)
    except ValueError:
        return None


def _ensure_bin(url: str) -> str:
    """Append LH_BIN=1 to *url* if not already present."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    if "LH_BIN" not in params:
        params["LH_BIN"] = ["1"]
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class EbayScraper(BaseScraper):
    """HTML scraper for eBay search results pages (Buy It Now only)."""

    name = "ebay"

    def _get_user_agent(self) -> str:
        if getattr(self.general_config, "user_agents_rotation", True):
            try:
                from fake_useragent import UserAgent

                return UserAgent().chrome
            except Exception:
                pass
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._get_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def _fetch_with_config(self, url: str) -> requests.Response:
        """Fetch *url* applying retry settings from general_config."""
        max_retries = getattr(self.general_config, "max_retries", 3)
        backoff = getattr(self.general_config, "retry_backoff_seconds", 5)
        timeout = getattr(self.general_config, "request_timeout_seconds", 30)

        fetch_fn = retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_fixed(backoff),
            reraise=True,
        )(self._do_get)

        return fetch_fn(url, timeout)

    def _do_get(self, url: str, timeout: int) -> requests.Response:
        return requests.get(
            url,
            headers=self._build_headers(),
            timeout=timeout,
            allow_redirects=True,
        )

    def _dump_debug_html(self, html: str) -> None:
        """Write HTML to logs/debug_ebay.html (max 1 MB) for debugging."""
        try:
            logs_dir = Path("logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
            debug_path = logs_dir / "debug_ebay.html"
            content = html.encode("utf-8", errors="replace")[:_DEBUG_MAX_BYTES]
            debug_path.write_bytes(content)
            logger.debug("Debug HTML written to {path}", path=debug_path)
        except Exception as exc:
            logger.debug("Could not write debug HTML: {exc}", exc=exc)

    def _select_first(self, tag: Any, selectors: list[str]) -> Any | None:
        """Try each selector in order and return the first match, or None."""
        for sel in selectors:
            result = tag.select_one(sel)
            if result:
                return result
        return None

    def _parse_card(self, card: Any, base_url: str) -> dict | None:
        """Extract raw data from a single eBay listing item.

        Returns a dict with keys: title, price, url, in_stock.
        Returns None if the item should be skipped (dummy header, auction, sold).
        """
        # Title
        title_tag = self._select_first(card, _TITLE_SELECTORS)
        if title_tag is None:
            return None
        title = title_tag.get_text(strip=True)
        if not title:
            return None

        # Skip the dummy "Shop on eBay" header item
        if title.lower() == _DUMMY_TITLE:
            return None

        # Skip auction items (we want BIN only)
        secondary_info = card.select_one(".SECONDARY_INFO")
        listing_type = (
            secondary_info.get_text(strip=True).lower() if secondary_info else ""
        )
        if "auction" in listing_type:
            return None

        # Price
        price_tag = self._select_first(card, _PRICE_SELECTORS)
        price = _parse_price(price_tag.get_text(strip=True) if price_tag else None)

        # URL — from the item link
        link_tag = card.select_one("a.s-item__link") or card.select_one(
            "a[href*='/itm/']"
        )
        href = link_tag.get("href", "") if link_tag else ""
        url = href if href.startswith("http") else urljoin(base_url, href)

        # Stock: BIN listings are generally available unless marked "Sold"
        sold_tag = card.select_one(".s-item__caption--signal")
        is_sold = (
            sold_tag is not None and "sold" in sold_tag.get_text(strip=True).lower()
        )
        in_stock = not is_sold

        return {
            "title": title,
            "price": price,
            "url": url,
            "in_stock": in_stock,
        }

    def search(self, product: Product, search_url: str) -> list[PriceCheck]:
        """Fetch eBay search page and return filtered PriceCheck results.

        Automatically appends LH_BIN=1 to restrict to Buy It Now listings.
        Returns an empty list (without raising) on HTTP errors.
        Skips dummy header items, auction listings, and sold items.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # Ensure Buy It Now filter is applied
        url = _ensure_bin(search_url)

        try:
            response = self._fetch_with_config(url)
        except Exception as exc:
            logger.warning(
                "eBay fetch failed for {url}: {exc}",
                url=url,
                exc=exc,
            )
            return []

        if response.status_code >= 400:
            logger.warning(
                "eBay returned HTTP {status} for {url} — skipping",
                status=response.status_code,
                url=url,
            )
            return []

        html = response.text
        soup = BeautifulSoup(html, "lxml")

        # Find listing items using fallback selector chain
        cards: list[Any] = []
        for sel in _CARD_SELECTORS:
            cards = soup.select(sel)
            if cards:
                break

        if not cards:
            logger.warning(
                "No listing items found on eBay results page for {url}",
                url=url,
            )
            self._dump_debug_html(html)
            return []

        # Parse each card
        raw_results: list[dict] = []
        for card in cards:
            try:
                raw = self._parse_card(card, _BASE_URL)
                if raw is not None:
                    raw_results.append(raw)
            except Exception as exc:
                logger.debug(
                    "Skipping malformed eBay card: {exc}",
                    exc=exc,
                )
                continue

        # Apply must_have / blocklist filters
        filtered = self.filter_results(raw_results, product)

        if not filtered:
            logger.warning(
                "eBay: zero results after filtering for SKU={sku}",
                sku=product.sku,
            )
            self._dump_debug_html(html)
            return []

        # Convert to PriceCheck objects
        checks: list[PriceCheck] = []
        for item in filtered:
            matched = [
                term
                for term in product.must_have_terms
                if term.lower() in item["title"].lower()
            ]
            checks.append(
                PriceCheck(
                    product_sku=product.sku,
                    store=self.name,
                    timestamp=timestamp,
                    success=True,
                    price=item["price"],
                    url=item["url"],
                    in_stock=item["in_stock"],
                    raw_title=item["title"],
                    matched_terms=matched,
                    error=None,
                )
            )

        logger.info(
            "eBay: found {n} result(s) for SKU={sku}",
            n=len(checks),
            sku=product.sku,
        )
        return checks
