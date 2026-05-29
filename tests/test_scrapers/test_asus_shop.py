"""
Tests for src/scrapers/asus_shop.py

HTTP layer is mocked via pytest-mock (mocker.patch).
The fixture HTML is read from tests/fixtures/asus_shop_sample.html.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.models import Product
from src.scrapers.asus_shop import ASUSShopScraper, _parse_price

# ---------------------------------------------------------------------------
# Paths & helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_HTML = (FIXTURES_DIR / "asus_shop_sample.html").read_text(encoding="utf-8")
SEARCH_URL = "https://shop.asus.com/us/search?q=UX3405CA-PS99T"


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
        target_price=1299.00,
        must_have_terms=must_have if must_have is not None else ["120Hz", "32GB", "285H"],
        blocklist_terms=blocklist if blocklist is not None else ["FHD+", "60Hz"],
        stores={"asus_shop": SEARCH_URL},
    )


def _make_scraper() -> ASUSShopScraper:
    general = MagicMock()
    general.user_agents_rotation = False
    general.request_timeout_seconds = 10
    general.max_retries = 1
    general.retry_backoff_seconds = 0
    store_cfg = MagicMock()
    return ASUSShopScraper(store_cfg, general)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearchParsesMatchingProduct:
    """ASUSShopScraper.search() returns only cards that pass the product filters."""

    def test_search_parses_matching_product(self, mocker):
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
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
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        assert len(results) >= 1
        assert results[0].price == 1399.0

    def test_in_stock_flag_set(self, mocker):
        """Card with add-to-cart button and no Out-of-Stock text should have in_stock=True."""
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        assert results[0].in_stock is True


class TestBlocklistedProductFiltered:
    """Blocklisted products must not appear in results."""

    def test_blocklisted_product_filtered(self, mocker):
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        titles = [r.raw_title for r in results]
        assert not any("60Hz" in t or "FHD+" in t for t in titles)

    def test_out_of_stock_card_still_returned_with_flag(self, mocker):
        """Card marked Out-of-Stock that passes filters should have in_stock=False."""
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        # Must-have: 285H 32GB 120Hz — the OOS card in fixture matches these
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        oos_results = [r for r in results if r.in_stock is False]
        # There should be an out-of-stock result for the 2TB OOS card
        assert len(oos_results) >= 1


class TestHttpErrorReturnsEmpty:
    """HTTP errors should return [] without raising."""

    def test_http_503_returns_empty(self, mocker):
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response("", 503),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []

    def test_http_404_returns_empty(self, mocker):
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response("", 404),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []

    def test_request_exception_returns_empty(self, mocker):
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
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
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response(empty_html),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []


class TestParsePriceUnit:
    """Unit tests for the _parse_price helper."""

    def test_standard_price_with_dollar(self):
        assert _parse_price("$1,399.00") == 1399.0

    def test_price_without_dollar(self):
        assert _parse_price("1399.00") == 1399.0

    def test_price_without_cents(self):
        assert _parse_price("$1,399") == 1399.0

    def test_none_input(self):
        assert _parse_price(None) is None

    def test_empty_string(self):
        assert _parse_price("") is None
