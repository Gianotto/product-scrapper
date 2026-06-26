"""
Best Buy HTML scraper.

Fetches a Best Buy search-results page and parses product cards.
Uses a CSS-selector fallback chain to handle minor site layout changes.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

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


# ---------------------------------------------------------------------------
# Price parser
# ---------------------------------------------------------------------------


def _parse_price(text: str | None) -> float | None:
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
    _referer = "https://www.bestbuy.com/"
    _debug_html_name = "debug_bestbuy.html"

    def _parse_card(self, card: Any, base_url: str) -> dict | None:
        title_tag = self._select_first(card, _TITLE_SELECTORS)
        if title_tag is None:
            return None
        title = title_tag.get_text(strip=True)
        if not title:
            return None

        price_tag = self._select_first(card, _PRICE_SELECTORS)
        price = _parse_price(price_tag.get_text(strip=True) if price_tag else None)

        href = title_tag.get("href", "")
        url = urljoin(base_url, href) if href else base_url

        cart_btn = card.select_one("button.add-to-cart-button")
        sold_out_text = "sold out" in card.get_text().lower()
        in_stock = cart_btn is not None or not sold_out_text

        return {"title": title, "price": price, "url": url, "in_stock": in_stock}

    def search(self, product: Product, search_url: str) -> list[PriceCheck]:
        """Fetch Best Buy search page and return filtered PriceCheck results.

        Returns an empty list (without raising) on HTTP 429 / 503.
        Skips individual cards that raise any parsing exception.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            response = self._fetch_with_config(search_url)
        except Exception as exc:
            logger.warning("BestBuy fetch failed for {url}: {exc}", url=search_url, exc=exc)
            return []

        if response.status_code in (429, 503):
            logger.warning(
                "BestBuy returned HTTP {status} for {url} — skipping",
                status=response.status_code,
                url=search_url,
            )
            return []

        html = response.text
        soup = BeautifulSoup(html, "lxml")

        # Detect geo-block / bot-challenge: BestBuy shows country selector or serves
        # a tiny Akamai challenge page instead of real search results
        page_title = soup.find("title")
        title_text = page_title.get_text().lower() if page_title else ""
        if "international" in title_text or "select your country" in title_text:
            logger.warning(
                "BestBuy: geo-blocked (country selector) for {url} — "
                "non-US IP detected; scraping not possible without a US proxy",
                url=search_url,
            )
            return []

        # If the page is tiny (< 20 KB) and has no recognisable BestBuy structure,
        # it is likely an Akamai bot-challenge page
        if len(html) < 20_000 and not soup.find(class_=lambda c: c and "sku" in c):
            logger.warning(
                "BestBuy: bot-challenge or incomplete page received for {url} "
                "(page size={size} bytes) — skipping",
                url=search_url,
                size=len(html),
            )
            return []

        cards: list[Any] = []
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

        raw_results: list[dict] = []
        for card in cards:
            try:
                raw = self._parse_card(card, _BASE_URL)
                if raw is not None:
                    raw_results.append(raw)
            except Exception as exc:
                logger.debug("Skipping malformed card: {exc}", exc=exc)
                continue

        filtered = self.filter_results(raw_results, product)

        if not filtered:
            logger.warning(
                "BestBuy: zero results after filtering for SKU={sku}", sku=product.sku
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

        logger.info("BestBuy: found {n} result(s) for SKU={sku}", n=len(checks), sku=product.sku)
        return checks
