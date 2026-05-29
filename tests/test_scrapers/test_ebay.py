"""
Tests for src/scrapers/ebay.py

HTTP layer is mocked via pytest-mock (mocker.patch).
The fixture HTML is read from tests/fixtures/ebay_sample.html.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.models import Product
from src.scrapers.ebay import EbayScraper, _parse_price, _ensure_bin

# ---------------------------------------------------------------------------
# Paths & helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_HTML = (FIXTURES_DIR / "ebay_sample.html").read_text(encoding="utf-8")
SEARCH_URL = "https://www.ebay.com/sch/i.html?_nkw=asus+zenbook+14+oled"


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
        stores={"ebay": SEARCH_URL},
    )


def _make_scraper() -> EbayScraper:
    general = MagicMock()
    general.user_agents_rotation = False
    general.request_timeout_seconds = 10
    general.max_retries = 1
    general.retry_backoff_seconds = 0
    store_cfg = MagicMock()
    return EbayScraper(store_cfg, general)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearchParsesMatchingProduct:
    """EbayScraper.search() returns only cards that pass the product filters."""

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
        assert results[0].price == 1249.99

    def test_bin_param_appended_to_url(self, mocker):
        """search() should append LH_BIN=1 to the URL if not present."""
        mock_get = mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        product = _make_product()
        scraper.search(product, SEARCH_URL)

        called_url = mock_get.call_args[0][0]
        assert "LH_BIN=1" in called_url

    def test_bin_param_not_duplicated(self, mocker):
        """If LH_BIN=1 is already in URL, it should not be duplicated."""
        url_with_bin = SEARCH_URL + "&LH_BIN=1"
        result = _ensure_bin(url_with_bin)
        assert result.count("LH_BIN=1") == 1


class TestAuctionOrDummyItemsSkipped:
    """Dummy header items and auction listings should be excluded."""

    def test_dummy_shop_on_ebay_item_skipped(self, mocker):
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        titles = [r.raw_title for r in results]
        assert "Shop on eBay" not in titles

    def test_auction_item_skipped(self, mocker):
        """Listings with 'Auction' as secondary info should be skipped."""
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        # Use empty blocklist so the auction item would match if not filtered
        product = _make_product(must_have=["285H", "32GB", "120Hz"], blocklist=[])
        results = scraper.search(product, SEARCH_URL)

        titles = [r.raw_title for r in results]
        assert not any("Auction" in t for t in titles)


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
        empty_html = "<html><body><ul class='srp-results'></ul></body></html>"
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response(empty_html),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []


class TestParsePriceUnit:
    """Unit tests for price parsing helper."""

    def test_standard_price(self):
        assert _parse_price("$1,249.99") == 1249.99

    def test_no_comma(self):
        assert _parse_price("$899.00") == 899.0

    def test_price_range_takes_lower(self):
        """Price range like '$900.00 to $1,200.00' should return the lower value."""
        result = _parse_price("$900.00 to $1,200.00")
        assert result == 900.0

    def test_none_input(self):
        assert _parse_price(None) is None

    def test_empty_string(self):
        assert _parse_price("") is None


class TestEnsureBinHelper:
    """Unit tests for _ensure_bin URL helper."""

    def test_adds_bin_param_when_missing(self):
        url = "https://www.ebay.com/sch/i.html?_nkw=asus"
        result = _ensure_bin(url)
        assert "LH_BIN=1" in result

    def test_preserves_existing_bin_param(self):
        url = "https://www.ebay.com/sch/i.html?_nkw=asus&LH_BIN=1"
        result = _ensure_bin(url)
        assert result.count("LH_BIN") == 1

    def test_preserves_other_params(self):
        url = "https://www.ebay.com/sch/i.html?_nkw=asus&LH_ItemCondition=1000"
        result = _ensure_bin(url)
        assert "LH_ItemCondition=1000" in result
        assert "LH_BIN=1" in result
