"""
eBay scraper.

Uses the eBay Finding API when EBAY_API_KEY is set in the environment and
``use_api: true`` is configured for the ebay store — this is more reliable
and avoids bot-detection issues.

Falls back to HTML scraping of the search-results page (Buy It Now only)
when the API is not configured.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup
from loguru import logger

from src.models import PriceCheck, Product
from src.scrapers.base import BaseScraper

# ---------------------------------------------------------------------------
# Constants
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
_DUMMY_TITLE = "shop on ebay"

# eBay Finding API endpoint (free, requires App ID from developer.ebay.com)
_FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
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
    """eBay scraper — uses Finding API when configured, HTML scraping otherwise."""

    name = "ebay"
    _referer = "https://www.ebay.com/"
    _debug_html_name = "debug_ebay.html"

    # ------------------------------------------------------------------
    # Finding API path
    # ------------------------------------------------------------------

    def _extract_keywords(self, search_url: str, product: Product) -> str:
        """Extract keywords from the eBay search URL (_nkw param), or use the SKU."""
        parsed = urlparse(search_url)
        params = parse_qs(parsed.query)
        nkw = params.get("_nkw", [""])[0]
        return nkw or product.sku

    def _search_via_api(
        self, product: Product, keywords: str, timestamp: str
    ) -> list[PriceCheck]:
        """Call the eBay Finding API and return filtered PriceCheck results.

        Returns an empty list on API failure or when no results match filters.
        """
        app_id = os.environ.get("EBAY_API_KEY") or os.environ.get("EBAY_APP_ID", "")
        if not app_id:
            logger.warning(
                "eBay use_api=true but EBAY_API_KEY is not set — falling back to HTML scraping"
            )
            return []

        params = {
            "OPERATION-NAME": "findItemsByKeywords",
            "SERVICE-VERSION": "1.0.0",
            "SECURITY-APPNAME": app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "keywords": keywords,
            "itemFilter(0).name": "ListingType",
            "itemFilter(0).value": "FixedPrice",
            "itemFilter(1).name": "Condition",
            "itemFilter(1).value": "1000",  # New
            "sortOrder": "PricePlusShippingLowest",
            "paginationInput.entriesPerPage": "10",
        }

        try:
            resp = self._session.get(_FINDING_API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("eBay Finding API request failed: {exc}", exc=exc)
            return []

        try:
            items = (
                data.get("findItemsByKeywordsResponse", [{}])[0]
                .get("searchResult", [{}])[0]
                .get("item", [])
            )
        except (IndexError, KeyError):
            items = []

        raw_results: list[dict] = []
        for item in items:
            try:
                title = item.get("title", [""])[0]
                price_str = (
                    item.get("sellingStatus", [{}])[0]
                    .get("currentPrice", [{}])[0]
                    .get("__value__", "")
                )
                price = float(price_str) if price_str else None
                url = item.get("viewItemURL", [""])[0]
                listing_type = (
                    item.get("listingInfo", [{}])[0].get("listingType", [""])[0].lower()
                )
                if "auction" in listing_type:
                    continue
                raw_results.append(
                    {"title": title, "price": price, "url": url, "in_stock": price is not None}
                )
            except (IndexError, KeyError, ValueError):
                continue

        filtered = self.filter_results(raw_results, product)

        if not filtered:
            logger.warning(
                "eBay API: zero results after filtering for SKU={sku}", sku=product.sku
            )
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

        logger.info(
            "eBay API: found {n} result(s) for SKU={sku}", n=len(checks), sku=product.sku
        )
        return checks

    # ------------------------------------------------------------------
    # HTML scraping path
    # ------------------------------------------------------------------

    def _parse_card(self, card: Any, base_url: str) -> dict | None:
        title_tag = self._select_first(card, _TITLE_SELECTORS)
        if title_tag is None:
            return None
        title = title_tag.get_text(strip=True)
        if not title:
            return None

        if title.lower() == _DUMMY_TITLE:
            return None

        secondary_info = card.select_one(".SECONDARY_INFO")
        listing_type = (
            secondary_info.get_text(strip=True).lower() if secondary_info else ""
        )
        if "auction" in listing_type:
            return None

        price_tag = self._select_first(card, _PRICE_SELECTORS)
        price = _parse_price(price_tag.get_text(strip=True) if price_tag else None)

        link_tag = card.select_one("a.s-item__link") or card.select_one("a[href*='/itm/']")
        href = link_tag.get("href", "") if link_tag else ""
        url = href if href.startswith("http") else urljoin(base_url, href)

        sold_tag = card.select_one(".s-item__caption--signal")
        is_sold = sold_tag is not None and "sold" in sold_tag.get_text(strip=True).lower()
        in_stock = not is_sold

        return {"title": title, "price": price, "url": url, "in_stock": in_stock}

    def search(self, product: Product, search_url: str) -> list[PriceCheck]:
        """Search eBay for *product*.

        Uses the Finding API when ``use_api=true`` and EBAY_API_KEY is set.
        Falls back to HTML scraping with Buy It Now filter otherwise.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        if getattr(self.config, "use_api", False):
            keywords = self._extract_keywords(search_url, product)
            results = self._search_via_api(product, keywords, timestamp)
            if results or os.environ.get("EBAY_API_KEY") or os.environ.get("EBAY_APP_ID"):
                return results
            # Key was not set — fall through to HTML scraping

        url = _ensure_bin(search_url)

        try:
            response = self._fetch_with_config(url)
        except Exception as exc:
            logger.warning("eBay fetch failed for {url}: {exc}", url=url, exc=exc)
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

        cards: list[Any] = []
        for sel in _CARD_SELECTORS:
            cards = soup.select(sel)
            if cards:
                break

        if not cards:
            logger.warning(
                "No listing items found on eBay results page for {url}", url=url
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
                logger.debug("Skipping malformed eBay card: {exc}", exc=exc)
                continue

        filtered = self.filter_results(raw_results, product)

        if not filtered:
            logger.warning(
                "eBay: zero results after filtering for SKU={sku}", sku=product.sku
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

        logger.info("eBay: found {n} result(s) for SKU={sku}", n=len(checks), sku=product.sku)
        return checks
