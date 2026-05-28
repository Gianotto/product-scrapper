"""
Tests for src/scrapers/newegg.py

HTTP layer is mocked via pytest-mock (mocker.patch).
The fixture HTML is read from tests/fixtures/newegg_sample.html.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.models import PriceCheck, Product
from src.scrapers.newegg import NeweggScraper, _parse_price, _parse_newegg_price

# ---------------------------------------------------------------------------
# Paths & helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_HTML = (FIXTURES_DIR / "newegg_sample.html").read_text(encoding="utf-8")
SEARCH_URL = "https://www.newegg.com/p/pl?d=asus+zenbook+14+oled"


def _make_response(html: str, status_code: int = 200) -> MagicMock:
    """Build a minimal mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    resp.ok = 200 <= status_code < 300
    return resp


def _make_product(
    must_have: list[str] | None = None,
    blocklist: list[str] | None = None,
) -> Product:
    return Product(
        sku="UX3405CA-PS99T",
        name="ASUS Zenbook 14 OLED",
        target_price=1099.00,
        must_have_terms=must_have if must_have is not None else ["120Hz", "32GB", "285H"],
        blocklist_terms=blocklist if blocklist is not None else ["FHD+", "60Hz"],
        stores={"newegg": SEARCH_URL},
    )


def _make_scraper() -> NeweggScraper:
    general = MagicMock()
    general.user_agents_rotation = False
    general.request_timeout_seconds = 10
    general.max_retries = 1
    general.retry_backoff_seconds = 0
    store_cfg = MagicMock()
    return NeweggScraper(store_cfg, general)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearchParsesMatchingProduct:
    """NeweggScraper.search() returns only cards that pass the product filters."""

    def test_search_parses_matching_product(self, mocker):
        mocker.patch(
            "src.scrapers.newegg.requests.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        assert len(results) >= 1
        assert results[0].success is True
        assert "285H" in results[0].raw_title
        assert "32GB" in results[0].raw_title
        assert "120Hz" in results[0].raw_title

    def test_price_parsed_correctly(self, mocker):
        """Newegg split price (<strong>1,299</strong><sup>.00</sup>) parses to 1299.0."""
        mocker.patch(
            "src.scrapers.newegg.requests.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        assert len(results) >= 1
        assert results[0].price == 1299.0

    def test_in_stock_flag_set(self, mocker):
        """Card with Add-to-Cart and no OUT OF STOCK text should have in_stock=True."""
        mocker.patch(
            "src.scrapers.newegg.requests.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        in_stock_results = [r for r in results if r.in_stock]
        assert len(in_stock_results) >= 1


class TestBlocklistedProductFiltered:
    """Blocklisted products must not appear in results."""

    def test_blocklisted_product_filtered(self, mocker):
        mocker.patch(
            "src.scrapers.newegg.requests.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        titles = [r.raw_title for r in results]
        assert not any("60Hz" in t or "FHD+" in t for t in titles)

    def test_sponsored_item_skipped(self, mocker):
        """Items with item-sponsored class should be filtered out."""
        mocker.patch(
            "src.scrapers.newegg.requests.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        urls = [r.url for r in results]
        assert not any("SPONSORED" in (u or "") for u in urls)


class TestHttpErrorReturnsEmpty:
    """HTTP errors should return [] without raising."""

    def test_http_503_returns_empty(self, mocker):
        mocker.patch(
            "src.scrapers.newegg.requests.get",
            return_value=_make_response("", 503),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []

    def test_http_404_returns_empty(self, mocker):
        mocker.patch(
            "src.scrapers.newegg.requests.get",
            return_value=_make_response("", 404),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []

    def test_request_exception_returns_empty(self, mocker):
        mocker.patch(
            "src.scrapers.newegg.requests.get",
            side_effect=Exception("Connection refused"),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []


class TestNoResultsReturnsEmpty:
    """Empty search result page should return []."""

    def test_no_results_returns_empty(self, mocker):
        empty_html = "<html><body><div class='no-results'>No products found.</div></body></html>"
        mocker.patch(
            "src.scrapers.newegg.requests.get",
            return_value=_make_response(empty_html),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []


class TestParsePriceUnit:
    """Unit tests for price parsing helpers."""

    def test_standard_price(self):
        assert _parse_price("$1,299.00") == 1299.0

    def test_no_comma(self):
        assert _parse_price("$899.00") == 899.0

    def test_none_input(self):
        assert _parse_price(None) is None

    def test_empty_string(self):
        assert _parse_price("") is None

    def test_newegg_split_price(self):
        """Test _parse_newegg_price with a mock BS4 tag structure."""
        from bs4 import BeautifulSoup

        html = '<li class="price-current"><strong>1,299</strong><sup>.00</sup></li>'
        soup = BeautifulSoup(html, "lxml")
        container = soup.select_one(".price-current")
        assert _parse_newegg_price(container) == 1299.0

    def test_newegg_price_none_container(self):
        assert _parse_newegg_price(None) is None
