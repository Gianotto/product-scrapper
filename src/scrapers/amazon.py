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
from typing import Any

from bs4 import BeautifulSoup
from loguru import logger

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned)
    except ValueError:
        return None


def _detect_block(html: str) -> str | None:
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
    _referer = "https://www.amazon.com/"
    _debug_html_name = "debug_amazon.html"

    def _parse_card(self, card: Any, base_url: str) -> dict | None:
        asin = card.get("data-asin", "").strip()
        if not asin:
            return None

        title_tag = self._select_first(card, _TITLE_SELECTORS)
        if title_tag is None:
            return None
        title = title_tag.get_text(strip=True)
        if not title:
            return None

        price_tag = self._select_first(card, _PRICE_SELECTORS)
        price = _parse_price(price_tag.get_text(strip=True) if price_tag else None)

        if price is None:
            whole_tag = card.select_one(".a-price-whole")
            frac_tag = card.select_one(".a-price-fraction")
            if whole_tag:
                whole = whole_tag.get_text(strip=True).replace(",", "").rstrip(".")
                frac = frac_tag.get_text(strip=True) if frac_tag else "00"
                price = _parse_price(f"{whole}.{frac}")

        url = f"{base_url}/dp/{asin}"
        in_stock = price is not None  # no price selector hit → assume out of stock

        return {"title": title, "price": price, "url": url, "in_stock": in_stock, "asin": asin}

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
            logger.warning("Amazon fetch failed for {url}: {exc}", url=search_url, exc=exc)
            return []
        finally:
            time.sleep(_MIN_DELAY_SECONDS)

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

        block_reason = _detect_block(html)
        if block_reason:
            logger.warning("{reason} for {url}", reason=block_reason, url=search_url)
            return []

        soup = BeautifulSoup(html, "lxml")

        cards: list[Any] = []
        for sel in _CARD_SELECTORS:
            cards = soup.select(sel)
            if cards:
                break

        if not cards:
            logger.warning(
                "No product cards found on Amazon results page for {url}", url=search_url
            )
            self._dump_debug_html(html)
            return []

        raw_results: list[dict] = []
        for card in cards:
            try:
                raw = self._parse_card(card, _BASE_URL)
                if raw is not None:
                    raw_results.append(raw)
            except Exception as exc:
                logger.debug("Skipping malformed Amazon card: {exc}", exc=exc)
                continue

        filtered = self.filter_results(raw_results, product)

        if not filtered:
            logger.warning(
                "Amazon: zero results after filtering for SKU={sku}", sku=product.sku
            )
            self._dump_debug_html(html)
            return []

        checks: list[PriceCheck] = []
        for item in filtered:
            matched = [
                term for term in product.must_have_terms if term.lower() in item["title"].lower()
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

        logger.info("Amazon: found {n} result(s) for SKU={sku}", n=len(checks), sku=product.sku)
        return checks
