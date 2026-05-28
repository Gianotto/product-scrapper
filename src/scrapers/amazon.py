"""
Amazon HTML scraper.

Fetches an Amazon search-results page and parses product cards.
Amazon has aggressive anti-bot measures; this scraper detects CAPTCHA and
block responses and returns an empty list gracefully rather than propagating
errors.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    "[data-component-type='s-search-result']",
    ".s-result-item[data-asin]",
]

_TITLE_SELECTORS = [
    "h2 a span",
    ".a-size-medium",
    ".a-text-normal",
]

_PRICE_SELECTORS = [
    ".a-price .a-offscreen",
]

_BASE_URL = "https://www.amazon.com"

# Strings that indicate Amazon has blocked the request
_CAPTCHA_STRINGS = [
    "sorry, we just need to make sure you're not a robot",
    "type the characters you see",
    "enter the characters you see",
]
_BLOCK_STRINGS = [
    "api-services-support",
]

# Minimum delay after Amazon requests to reduce rate-limiting
_MIN_DELAY_SECONDS = 5

# Maximum size of the debug HTML dump (1 MB)
_DEBUG_MAX_BYTES = 1 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_price(text: str | None) -> float | None:
    """Parse a price string like '$1,349.00' into a float, or return None."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned)
    except ValueError:
        return None


def _detect_block(html: str) -> str | None:
    """Return a description of the block type if detected, else None."""
    html_lower = html.lower()
    for phrase in _CAPTCHA_STRINGS:
        if phrase in html_lower:
            return "Amazon CAPTCHA detected"
    for phrase in _BLOCK_STRINGS:
        if phrase in html_lower:
            return "Amazon block detected (api-services-support)"
    return None


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class AmazonScraper(BaseScraper):
    """HTML scraper for Amazon search results pages."""

    name = "amazon"

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
        """Write HTML to logs/debug_amazon.html (max 1 MB) for debugging."""
        try:
            logs_dir = Path("logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
            debug_path = logs_dir / "debug_amazon.html"
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
        """Extract raw data from a single Amazon search result card.

        Returns a dict with keys: title, price, url, in_stock, asin.
        Returns None if essential data is missing.
        """
        # ASIN
        asin = card.get("data-asin", "").strip()
        if not asin:
            return None

        # Title
        title_tag = self._select_first(card, _TITLE_SELECTORS)
        if title_tag is None:
            return None
        title = title_tag.get_text(strip=True)
        if not title:
            return None

        # Price — prefer .a-offscreen for accuracy
        price_tag = self._select_first(card, _PRICE_SELECTORS)
        price = _parse_price(price_tag.get_text(strip=True) if price_tag else None)

        # If no price from offscreen, try whole + fraction
        if price is None:
            whole_tag = card.select_one(".a-price-whole")
            frac_tag = card.select_one(".a-price-fraction")
            if whole_tag:
                whole = whole_tag.get_text(strip=True).replace(",", "").rstrip(".")
                frac = frac_tag.get_text(strip=True) if frac_tag else "00"
                price = _parse_price(f"{whole}.{frac}")

        # URL — build from ASIN for a canonical product page
        url = f"{base_url}/dp/{asin}"

        # Stock: if price found → in_stock; if no price → out_of_stock
        in_stock = price is not None  # no price selector hit → assume out of stock

        return {
            "title": title,
            "price": price,
            "url": url,
            "in_stock": in_stock,
            "asin": asin,
        }

    def search(self, product: Product, search_url: str) -> list[PriceCheck]:
        """Fetch Amazon search page and return filtered PriceCheck results.

        Detects and handles CAPTCHA / bot-block responses gracefully.
        Returns an empty list (without raising) on HTTP 503 or block detection.
        Applies a minimum delay after the request to reduce rate-limiting.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            response = self._fetch_with_config(search_url)
        except Exception as exc:
            logger.warning(
                "Amazon fetch failed for {url}: {exc}",
                url=search_url,
                exc=exc,
            )
            return []
        finally:
            # Always wait the minimum delay after attempting an Amazon request
            time.sleep(_MIN_DELAY_SECONDS)

        # Handle 503 (bot block)
        if response.status_code == 503:
            logger.warning("Amazon blocked (503) for {url}", url=search_url)
            return []

        if response.status_code >= 400:
            logger.warning(
                "Amazon returned HTTP {status} for {url} — skipping",
                status=response.status_code,
                url=search_url,
            )
            return []

        html = response.text

        # Detect CAPTCHA / block pages
        block_reason = _detect_block(html)
        if block_reason:
            logger.warning("{reason} for {url}", reason=block_reason, url=search_url)
            return []

        soup = BeautifulSoup(html, "lxml")

        # Find product cards using fallback selector chain
        cards: list[Any] = []
        for sel in _CARD_SELECTORS:
            cards = soup.select(sel)
            if cards:
                break

        if not cards:
            logger.warning(
                "No product cards found on Amazon results page for {url}",
                url=search_url,
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
                    "Skipping malformed Amazon card: {exc}",
                    exc=exc,
                )
                continue

        # Apply must_have / blocklist filters
        filtered = self.filter_results(raw_results, product)

        if not filtered:
            logger.warning(
                "Amazon: zero results after filtering for SKU={sku}",
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
            "Amazon: found {n} result(s) for SKU={sku}",
            n=len(checks),
            sku=product.sku,
        )
        return checks
