"""
Tests for src/scrapers/amazon.py

HTTP layer is mocked via pytest-mock (mocker.patch).
The fixture HTML is read from tests/fixtures/amazon_sample.html.
time.sleep is patched to avoid 5-second delays in tests.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.models import Product
from src.scrapers.amazon import AmazonScraper, _parse_price, _detect_block

# ---------------------------------------------------------------------------
# Paths & helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_HTML = (FIXTURES_DIR / "amazon_sample.html").read_text(encoding="utf-8")
SEARCH_URL = "https://www.amazon.com/s?k=ASUS+Zenbook+14+OLED+UX3405CA"


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
        stores={"amazon": SEARCH_URL},
    )


def _make_scraper() -> AmazonScraper:
    general = MagicMock()
    general.user_agents_rotation = False
    general.request_timeout_seconds = 10
    general.max_retries = 1
    general.retry_backoff_seconds = 0
    store_cfg = MagicMock()
    return AmazonScraper(store_cfg, general)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearchParsesMatchingProduct:
    """AmazonScraper.search() returns only cards that pass the product filters."""

    def test_search_parses_matching_product(self, mocker):
        mocker.patch("src.scrapers.base.requests.Session.get", return_value=_make_response(SAMPLE_HTML))
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        assert len(results) >= 1
        assert results[0].success is True
        assert "285H" in results[0].raw_title
        assert "32GB" in results[0].raw_title
        assert "120Hz" in results[0].raw_title

    def test_price_parsed_correctly(self, mocker):
        mocker.patch("src.scrapers.base.requests.Session.get", return_value=_make_response(SAMPLE_HTML))
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        assert len(results) >= 1
        assert results[0].price == 1349.0

    def test_product_url_uses_asin(self, mocker):
        """Product URL should be the canonical /dp/{asin} URL."""
        mocker.patch("src.scrapers.base.requests.Session.get", return_value=_make_response(SAMPLE_HTML))
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        assert results[0].url == "https://www.amazon.com/dp/B0CZLP8ZXK"

    def test_in_stock_true_when_price_present(self, mocker):
        """Card with a price should have in_stock=True."""
        mocker.patch("src.scrapers.base.requests.Session.get", return_value=_make_response(SAMPLE_HTML))
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        priced = [r for r in results if r.price is not None]
        assert all(r.in_stock for r in priced)


class TestBlocklistedProductFiltered:
    """Blocklisted products must not appear in results."""

    def test_blocklisted_product_filtered(self, mocker):
        mocker.patch("src.scrapers.base.requests.Session.get", return_value=_make_response(SAMPLE_HTML))
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        titles = [r.raw_title for r in results]
        assert not any("60Hz" in t or "FHD+" in t for t in titles)

    def test_out_of_stock_card_has_no_price(self, mocker):
        """Card without price element should have in_stock=False."""
        mocker.patch("src.scrapers.base.requests.Session.get", return_value=_make_response(SAMPLE_HTML))
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        # Use must_have that matches the no-price card too
        product = _make_product(must_have=["285H", "32GB", "120Hz"], blocklist=["FHD+", "60Hz"])
        results = scraper.search(product, SEARCH_URL)

        oos = [r for r in results if not r.in_stock]
        assert len(oos) >= 1


class TestCaptchaDetectedReturnsEmpty:
    """CAPTCHA or bot-block pages should return []."""

    def test_captcha_page_returns_empty(self, mocker):
        captcha_html = (
            "<html><body>"
            "<p>Sorry, we just need to make sure you're not a robot</p>"
            "</body></html>"
        )
        mocker.patch("src.scrapers.base.requests.Session.get", return_value=_make_response(captcha_html))
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []

    def test_type_characters_captcha_returns_empty(self, mocker):
        captcha_html = (
            "<html><body>"
            "<p>Type the characters you see in this image</p>"
            "</body></html>"
        )
        mocker.patch("src.scrapers.base.requests.Session.get", return_value=_make_response(captcha_html))
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []

    def test_api_services_support_block_returns_empty(self, mocker):
        block_html = (
            "<html><body>"
            "<p>Error: api-services-support</p>"
            "</body></html>"
        )
        mocker.patch("src.scrapers.base.requests.Session.get", return_value=_make_response(block_html))
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []


class TestHttpErrorReturnsEmpty:
    """HTTP errors should return [] without raising."""

    def test_http_503_returns_empty(self, mocker):
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response("", 503),
        )
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []

    def test_http_429_returns_empty(self, mocker):
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response("", 429),
        )
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []

    def test_request_exception_returns_empty(self, mocker):
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            side_effect=Exception("Connection refused"),
        )
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []


class TestNoResultsReturnsEmpty:
    """Empty search result page should return []."""

    def test_no_results_returns_empty(self, mocker):
        empty_html = (
            "<html><body>"
            "<div class='s-main-slot'>No results for your search.</div>"
            "</body></html>"
        )
        mocker.patch("src.scrapers.base.requests.Session.get", return_value=_make_response(empty_html))
        mocker.patch("src.scrapers.amazon.time.sleep")
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)
        assert results == []


class TestParsePriceUnit:
    """Unit tests for price parsing helpers."""

    def test_standard_price(self):
        assert _parse_price("$1,349.00") == 1349.0

    def test_no_comma(self):
        assert _parse_price("$999.00") == 999.0

    def test_none_input(self):
        assert _parse_price(None) is None

    def test_empty_string(self):
        assert _parse_price("") is None


class TestDetectBlockUnit:
    """Unit tests for _detect_block helper."""

    def test_no_block_returns_none(self):
        assert _detect_block("<html><body>Normal search results</body></html>") is None

    def test_robot_check_detected(self):
        html = "Sorry, we just need to make sure you're not a robot"
        assert _detect_block(html) is not None

    def test_type_characters_detected(self):
        html = "Type the characters you see in the image below"
        assert _detect_block(html) is not None

    def test_enter_characters_detected(self):
        html = "Enter the characters you see in this image"
        assert _detect_block(html) is not None

    def test_api_services_support_detected(self):
        html = "Error contacting api-services-support"
        assert _detect_block(html) is not None
