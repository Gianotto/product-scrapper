"""
Newegg HTML scraper.

Fetches a Newegg search-results page and parses product cards.
Uses a CSS-selector fallback chain to handle minor site layout changes.
Newegg splits prices across two elements: <strong> (whole) and <sup> (fraction).
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
    ".item-cell",
    ".item-container",
]

_TITLE_SELECTORS = [
    "a.item-title",
    ".item-title",
]

_PRICE_CONTAINER_SELECTORS = [
    ".price-current",
    ".price-was-data",
]

_BASE_URL = "https://www.newegg.com"


# ---------------------------------------------------------------------------
# Price parsers
# ---------------------------------------------------------------------------


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_newegg_price(container: Any) -> float | None:
    """Parse Newegg's split price format: <strong>1,299</strong><sup>.00</sup>."""
    if container is None:
        return None

    strong_tag = container.select_one("strong")
    sup_tag = container.select_one("sup")

    if strong_tag:
        whole = strong_tag.get_text(strip=True).replace(",", "")
        fraction = sup_tag.get_text(strip=True).lstrip(".") if sup_tag else "00"
        try:
            return float(f"{whole}.{fraction}")
        except ValueError:
            pass

    return _parse_price(container.get_text(strip=True))


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class NeweggScraper(BaseScraper):
    """HTML scraper for Newegg search results pages."""

    name = "newegg"
    _referer = "https://www.newegg.com/"
    _debug_html_name = "debug_newegg.html"

    def _is_sponsored(self, card: Any) -> bool:
        return bool(card.select_one(".item-sponsored")) or "item-sponsored" in card.get(
            "class", []
        )

    def _parse_card(self, card: Any, base_url: str) -> dict | None:
        if self._is_sponsored(card):
            return None

        title_tag = self._select_first(card, _TITLE_SELECTORS)
        if title_tag is None:
            return None
        title = title_tag.get_text(strip=True)
        if not title:
            return None

        price_container = self._select_first(card, _PRICE_CONTAINER_SELECTORS)
        price = _parse_newegg_price(price_container)

        href = title_tag.get("href", "") if title_tag.name == "a" else ""
        if not href:
            link = card.select_one("a[href]")
            href = link.get("href", "") if link else ""
        url = urljoin(base_url, href) if href else base_url

        card_text = card.get_text()
        out_of_stock = "out of stock" in card_text.lower()
        cart_btn = card.select_one(".btn-primary")
        in_stock = cart_btn is not None and not out_of_stock

        return {"title": title, "price": price, "url": url, "in_stock": in_stock}

    def search(self, product: Product, search_url: str) -> list[PriceCheck]:
        """Fetch Newegg search page and return filtered PriceCheck results.

        Returns an empty list (without raising) on HTTP errors.
        Skips sponsored items and individual cards that raise any parsing exception.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            response = self._fetch_with_config(search_url)
        except Exception as exc:
            logger.warning("Newegg fetch failed for {url}: {exc}", url=search_url, exc=exc)
            return []

        if response.status_code >= 400:
            logger.warning(
                "Newegg returned HTTP {status} for {url} — skipping",
                status=response.status_code,
                url=search_url,
            )
            return []

        html = response.text
        soup = BeautifulSoup(html, "lxml")

        cards: list[Any] = []
        for sel in _CARD_SELECTORS:
            cards = soup.select(sel)
            if cards:
                break

        if not cards:
            logger.warning(
                "No product cards found on Newegg results page for {url}", url=search_url
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
                logger.debug("Skipping malformed Newegg card: {exc}", exc=exc)
                continue

        filtered = self.filter_results(raw_results, product)

        if not filtered:
            logger.warning(
                "Newegg: zero results after filtering for SKU={sku}", sku=product.sku
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

        logger.info("Newegg: found {n} result(s) for SKU={sku}", n=len(checks), sku=product.sku)
        return checks
