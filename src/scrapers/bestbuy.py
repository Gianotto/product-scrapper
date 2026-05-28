"""
Best Buy HTML scraper.

Fetches a Best Buy search-results page and parses product cards.
Uses a CSS-selector fallback chain to handle minor site layout changes.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

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
    ".sku-item",
    ".list-item",
    "[class*='sku-item']",
]

_TITLE_SELECTORS = [
    ".sku-title a",
    "h4.sku-header a",
    "[class*='sku-title'] a",
]

_PRICE_SELECTORS = [
    ".priceView-customer-price span:first-child",
    ".priceView-hero-price span:first-child",
    "[class*='priceView'] span",
]

_BASE_URL = "https://www.bestbuy.com"

# Maximum size of the debug HTML dump (1 MB)
_DEBUG_MAX_BYTES = 1 * 1024 * 1024


# ---------------------------------------------------------------------------
# Price parser
# ---------------------------------------------------------------------------


def _parse_price(text: str | None) -> float | None:
    """Parse a price string like '$1,299.00' into a float, or return None."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class BestBuyScraper(BaseScraper):
    """HTML scraper for Best Buy search results pages."""

    name = "bestbuy"

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

    @retry(
        stop=stop_after_attempt(3),  # overridden dynamically in search()
        wait=wait_fixed(5),
        reraise=True,
    )
    def _fetch(self, url: str, timeout: int) -> requests.Response:
        """Perform HTTP GET with retries.  Raises on non-2xx (except 429/503)."""
        return requests.get(
            url,
            headers=self._build_headers(),
            timeout=timeout,
            allow_redirects=True,
        )

    def _fetch_with_config(self, url: str) -> requests.Response:
        """Fetch *url* applying retry settings from general_config."""
        max_retries = getattr(self.general_config, "max_retries", 3)
        backoff = getattr(self.general_config, "retry_backoff_seconds", 5)
        timeout = getattr(self.general_config, "request_timeout_seconds", 30)

        # Rebuild a retry-decorated function using current config values
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
        """Write HTML to logs/debug_bestbuy.html (max 1 MB) for debugging."""
        try:
            logs_dir = Path("logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
            debug_path = logs_dir / "debug_bestbuy.html"
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

    def _parse_card(
        self,
        card: Any,
        base_url: str,
        product_sku: str,
        timestamp: str,
    ) -> dict | None:
        """Extract raw data from a single product card.

        Returns a dict with keys: title, price, url, in_stock.
        Returns None if essential data is missing.
        """
        # Title
        title_tag = self._select_first(card, _TITLE_SELECTORS)
        if title_tag is None:
            return None
        title = title_tag.get_text(strip=True)
        if not title:
            return None

        # Price
        price_tag = self._select_first(card, _PRICE_SELECTORS)
        price = _parse_price(price_tag.get_text(strip=True) if price_tag else None)

        # URL
        href = title_tag.get("href", "")
        url = urljoin(base_url, href) if href else base_url

        # Stock: presence of add-to-cart button OR absence of "Sold Out"
        cart_btn = card.select_one("button.add-to-cart-button")
        sold_out_text = "sold out" in card.get_text().lower()
        in_stock = cart_btn is not None or not sold_out_text

        return {
            "title": title,
            "price": price,
            "url": url,
            "in_stock": in_stock,
        }

    def search(self, product: Product, search_url: str) -> list[PriceCheck]:
        """Fetch Best Buy search page and return filtered PriceCheck results.

        Returns an empty list (without raising) on HTTP 429 / 503.
        Skips individual cards that raise any parsing exception.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            response = self._fetch_with_config(search_url)
        except Exception as exc:
            logger.warning(
                "BestBuy fetch failed for {url}: {exc}",
                url=search_url,
                exc=exc,
            )
            return []

        # Handle rate-limit / block responses gracefully
        if response.status_code in (429, 503):
            logger.warning(
                "BestBuy returned HTTP {status} for {url} — skipping",
                status=response.status_code,
                url=search_url,
            )
            return []

        html = response.text
        soup = BeautifulSoup(html, "lxml")

        # Find product cards using fallback selector chain
        cards = []
        for sel in _CARD_SELECTORS:
            cards = soup.select(sel)
            if cards:
                break

        if not cards:
            logger.warning(
                "No product cards found on BestBuy results page for {url}",
                url=search_url,
            )
            self._dump_debug_html(html)
            return []

        # Parse each card
        raw_results: list[dict] = []
        for card in cards:
            try:
                raw = self._parse_card(card, _BASE_URL, product.sku, timestamp)
                if raw is not None:
                    raw_results.append(raw)
            except Exception as exc:
                logger.debug(
                    "Skipping malformed card: {exc}",
                    exc=exc,
                )
                continue

        # Apply must_have / blocklist filters
        filtered = self.filter_results(raw_results, product)

        if not filtered:
            logger.warning(
                "BestBuy: zero results after filtering for SKU={sku}",
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
            "BestBuy: found {n} result(s) for SKU={sku}",
            n=len(checks),
            sku=product.sku,
        )
        return checks
