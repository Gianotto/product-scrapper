"""
Tests for src/scrapers/bestbuy.py

HTTP layer is mocked via pytest-mock (mocker.patch).
The fixture HTML is read from tests/fixtures/bestbuy_sample.html.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.models import PriceCheck, Product
from src.scrapers.base import pick_best_result
from src.scrapers.bestbuy import BestBuyScraper, _parse_price

# ---------------------------------------------------------------------------
# Paths & helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_HTML = (FIXTURES_DIR / "bestbuy_sample.html").read_text(encoding="utf-8")
SEARCH_URL = "https://www.bestbuy.com/site/searchpage.jsp?st=UX3405CA-PS99T"


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
        stores={"bestbuy": SEARCH_URL},
    )


def _make_scraper() -> BestBuyScraper:
    general = MagicMock()
    general.user_agents_rotation = False
    general.request_timeout_seconds = 10
    general.max_retries = 1
    general.retry_backoff_seconds = 0
    store_cfg = MagicMock()
    return BestBuyScraper(store_cfg, general)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearchReturnsMatchingResults:
    """BestBuyScraper.search() returns only cards that pass the product filters."""

    def test_search_returns_matching_results(self, mocker):
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        assert len(results) == 1
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

        assert len(results) == 1
        assert results[0].price == 1299.0

    def test_blocked_response_returns_empty(self, mocker):
        """HTTP 503 should return empty list without raising."""
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response("", 503),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        assert results == []

    def test_rate_limited_response_returns_empty(self, mocker):
        """HTTP 429 should return empty list without raising."""
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response("", 429),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        assert results == []

    def test_in_stock_flag_set(self, mocker):
        """Card with add-to-cart button should have in_stock=True."""
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response(SAMPLE_HTML),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        assert results[0].in_stock is True


class TestFilterResults:
    """BaseScraper.filter_results() applies must_have and blocklist correctly."""

    def test_filter_results_must_have(self):
        """Card missing a must_have term should be excluded."""
        scraper = _make_scraper()
        product = _make_product(must_have=["32GB", "285H", "120Hz"])

        results = [
            {"title": "ASUS Zenbook 14 OLED 32GB 285H 120Hz"},   # pass
            {"title": "ASUS Zenbook 14 OLED 16GB 285H 120Hz"},   # fail — missing 32GB
        ]
        filtered = scraper.filter_results(results, product)
        assert len(filtered) == 1
        assert "32GB" in filtered[0]["title"]

    def test_filter_results_blocklist(self):
        """Card with a blocklist term should be excluded."""
        scraper = _make_scraper()
        product = _make_product(must_have=["120Hz"], blocklist=["FHD+", "60Hz"])

        results = [
            {"title": "ASUS Zenbook 14 OLED 120Hz"},              # pass
            {"title": "ASUS Zenbook 14 OLED FHD+ 60Hz"},          # fail
        ]
        filtered = scraper.filter_results(results, product)
        assert len(filtered) == 1
        assert "FHD+" not in filtered[0]["title"]

    def test_filter_case_insensitive(self):
        """Filtering must be case-insensitive in both directions."""
        scraper = _make_scraper()
        product = _make_product(must_have=["120HZ"], blocklist=["REFURBISHED"])

        results = [
            {"title": "ASUS Zenbook 14 OLED 120hz"},                    # must_have lowercase
            {"title": "ASUS Zenbook 14 OLED 120Hz Refurbished"},        # blocklist mixed-case
        ]
        filtered = scraper.filter_results(results, product)
        assert len(filtered) == 1
        assert "120hz" in filtered[0]["title"].lower()

    def test_filter_empty_must_have(self):
        """No must_have terms means every card passes that check."""
        scraper = _make_scraper()
        product = _make_product(must_have=[], blocklist=[])
        results = [{"title": "Any laptop"}, {"title": "Another laptop"}]
        assert scraper.filter_results(results, product) == results

    def test_filter_missing_title_key(self):
        """Items without a title key are treated as empty string — fail must_have."""
        scraper = _make_scraper()
        product = _make_product(must_have=["32GB"], blocklist=[])
        results = [{"price": 999.0}]  # no "title" key
        assert scraper.filter_results(results, product) == []


class TestPickBestResult:
    """pick_best_result() selects the optimal PriceCheck."""

    def _check(self, price: float | None, in_stock: bool) -> PriceCheck:
        return PriceCheck(
            product_sku="SKU",
            store="bestbuy",
            timestamp="2025-01-01T00:00:00+00:00",
            success=True,
            price=price,
            in_stock=in_stock,
        )

    def test_pick_best_result_prefers_in_stock(self):
        """Cheapest in-stock result wins over cheaper out-of-stock."""
        checks = [
            self._check(800.0, False),   # cheaper but out of stock
            self._check(1100.0, True),   # in-stock, more expensive
            self._check(1050.0, True),   # in-stock, cheapest in-stock
        ]
        best = pick_best_result(checks)
        assert best is not None
        assert best.price == 1050.0
        assert best.in_stock is True

    def test_pick_best_result_falls_back_to_cheapest(self):
        """If nothing is in-stock, return cheapest overall."""
        checks = [
            self._check(1200.0, False),
            self._check(950.0, False),
        ]
        best = pick_best_result(checks)
        assert best is not None
        assert best.price == 950.0

    def test_pick_best_result_empty_list(self):
        assert pick_best_result([]) is None

    def test_pick_best_result_single(self):
        checks = [self._check(999.0, True)]
        best = pick_best_result(checks)
        assert best is not None
        assert best.price == 999.0

    def test_pick_best_result_none_price_skipped(self):
        """Checks with price=None don't count as 'cheapest'."""
        checks = [
            self._check(None, True),
            self._check(1199.0, True),
        ]
        best = pick_best_result(checks)
        assert best is not None
        assert best.price == 1199.0


class TestParseException:
    """Malformed cards should be skipped; other cards should still return."""

    def test_parse_exception_skips_card(self, mocker):
        """If one card is malformed, healthy cards still produce results."""
        # Build HTML with one valid card + one card missing the title link
        html = """
        <html><body>
          <li class="sku-item">
            <!-- no title anchor — will produce None from _parse_card -->
            <div class="priceView-customer-price"><span>$999.00</span></div>
          </li>
          <li class="sku-item">
            <div class="sku-title">
              <a href="/site/valid-product/123.p">ASUS Zenbook 14 OLED 32GB 285H 120Hz</a>
            </div>
            <div class="priceView-customer-price"><span>$1,299.00</span></div>
            <button class="add-to-cart-button">Add to Cart</button>
          </li>
        </html>
        """
        mocker.patch(
            "src.scrapers.base.requests.Session.get",
            return_value=_make_response(html),
        )
        scraper = _make_scraper()
        product = _make_product()
        results = scraper.search(product, SEARCH_URL)

        # Only the valid card should come through
        assert len(results) == 1
        assert results[0].price == 1299.0


class TestParsePriceUnit:
    """Unit tests for the _parse_price helper."""

    def test_standard_price(self):
        assert _parse_price("$1,299.00") == 1299.0

    def test_no_comma(self):
        assert _parse_price("$899.00") == 899.0

    def test_none_input(self):
        assert _parse_price(None) is None

    def test_empty_string(self):
        assert _parse_price("") is None

    def test_integer_price(self):
        assert _parse_price("$1000") == 1000.0
