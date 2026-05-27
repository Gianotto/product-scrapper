"""
Tests for src/models.py — creation, serialization, and deserialization
of Product, PriceCheck, and AlertEvent dataclasses.
"""

from __future__ import annotations

import pytest

from src.models import AlertEvent, PriceCheck, Product


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_product() -> Product:
    return Product(
        sku="UX3405CA-PS99T",
        name="ASUS Zenbook 14 OLED",
        target_price=1099.00,
        must_have_terms=["120Hz", "32GB"],
        blocklist_terms=["Refurbished"],
        stores={"bestbuy": "https://www.bestbuy.com/..."},
    )


@pytest.fixture()
def sample_check() -> PriceCheck:
    return PriceCheck(
        product_sku="UX3405CA-PS99T",
        store="bestbuy",
        timestamp="2025-05-27T10:00:00+00:00",
        success=True,
        price=1049.99,
        url="https://www.bestbuy.com/site/...",
        in_stock=True,
        raw_title="ASUS Zenbook 14 OLED 32GB 120Hz",
        matched_terms=["120Hz", "32GB"],
        error=None,
    )


@pytest.fixture()
def sample_alert() -> AlertEvent:
    return AlertEvent(
        product_sku="UX3405CA-PS99T",
        product_name="ASUS Zenbook 14 OLED",
        store="bestbuy",
        price=1049.99,
        target_price=1099.00,
        url="https://www.bestbuy.com/site/...",
        timestamp="2025-05-27T10:00:00+00:00",
        reason="below_target",
        previous_price=1149.00,
    )


# ---------------------------------------------------------------------------
# Product tests
# ---------------------------------------------------------------------------


class TestProduct:
    def test_creation(self, sample_product: Product) -> None:
        assert sample_product.sku == "UX3405CA-PS99T"
        assert sample_product.target_price == 1099.00
        assert "120Hz" in sample_product.must_have_terms
        assert "bestbuy" in sample_product.stores

    def test_to_dict(self, sample_product: Product) -> None:
        d = sample_product.to_dict()
        assert isinstance(d, dict)
        assert d["sku"] == "UX3405CA-PS99T"
        assert d["target_price"] == 1099.00
        assert d["must_have_terms"] == ["120Hz", "32GB"]
        assert d["blocklist_terms"] == ["Refurbished"]
        assert isinstance(d["stores"], dict)

    def test_from_dict_roundtrip(self, sample_product: Product) -> None:
        d = sample_product.to_dict()
        restored = Product.from_dict(d)
        assert restored == sample_product

    def test_from_dict_minimal(self) -> None:
        """from_dict should work when optional lists are absent."""
        d = {
            "sku": "TEST-SKU",
            "name": "Test Product",
            "target_price": "799.99",  # string — should be coerced to float
            "stores": {},
        }
        p = Product.from_dict(d)
        assert p.target_price == 799.99
        assert p.must_have_terms == []
        assert p.blocklist_terms == []

    def test_target_price_coercion(self) -> None:
        d = {
            "sku": "SKU",
            "name": "N",
            "target_price": "1234.56",
            "must_have_terms": [],
            "blocklist_terms": [],
            "stores": {},
        }
        p = Product.from_dict(d)
        assert isinstance(p.target_price, float)
        assert p.target_price == 1234.56


# ---------------------------------------------------------------------------
# PriceCheck tests
# ---------------------------------------------------------------------------


class TestPriceCheck:
    def test_creation(self, sample_check: PriceCheck) -> None:
        assert sample_check.product_sku == "UX3405CA-PS99T"
        assert sample_check.success is True
        assert sample_check.price == 1049.99
        assert sample_check.in_stock is True
        assert sample_check.error is None

    def test_defaults(self) -> None:
        check = PriceCheck(
            product_sku="SKU",
            store="amazon",
            timestamp="2025-01-01T00:00:00+00:00",
            success=False,
        )
        assert check.price is None
        assert check.url is None
        assert check.in_stock is False
        assert check.raw_title is None
        assert check.matched_terms == []
        assert check.error is None

    def test_to_dict(self, sample_check: PriceCheck) -> None:
        d = sample_check.to_dict()
        assert d["store"] == "bestbuy"
        assert d["price"] == 1049.99
        assert d["matched_terms"] == ["120Hz", "32GB"]

    def test_from_dict_roundtrip(self, sample_check: PriceCheck) -> None:
        d = sample_check.to_dict()
        restored = PriceCheck.from_dict(d)
        assert restored == sample_check

    def test_from_dict_with_none_price(self) -> None:
        d = {
            "product_sku": "SKU",
            "store": "newegg",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "success": False,
            "price": None,
            "url": None,
            "in_stock": False,
            "raw_title": None,
            "matched_terms": [],
            "error": "Timeout",
        }
        check = PriceCheck.from_dict(d)
        assert check.price is None
        assert check.error == "Timeout"

    def test_failed_check_has_error(self) -> None:
        check = PriceCheck(
            product_sku="SKU",
            store="ebay",
            timestamp="2025-01-01T00:00:00+00:00",
            success=False,
            error="Connection refused",
        )
        d = check.to_dict()
        assert d["error"] == "Connection refused"
        restored = PriceCheck.from_dict(d)
        assert restored.error == "Connection refused"


# ---------------------------------------------------------------------------
# AlertEvent tests
# ---------------------------------------------------------------------------


class TestAlertEvent:
    def test_creation(self, sample_alert: AlertEvent) -> None:
        assert sample_alert.reason == "below_target"
        assert sample_alert.price == 1049.99
        assert sample_alert.previous_price == 1149.00

    def test_to_dict(self, sample_alert: AlertEvent) -> None:
        d = sample_alert.to_dict()
        assert d["reason"] == "below_target"
        assert d["price"] == 1049.99
        assert d["previous_price"] == 1149.00

    def test_from_dict_roundtrip(self, sample_alert: AlertEvent) -> None:
        d = sample_alert.to_dict()
        restored = AlertEvent.from_dict(d)
        assert restored == sample_alert

    def test_optional_previous_price_none(self) -> None:
        alert = AlertEvent(
            product_sku="SKU",
            product_name="Name",
            store="amazon",
            price=800.00,
            target_price=899.00,
            url="https://example.com",
            timestamp="2025-01-01T00:00:00+00:00",
            reason="below_target",
        )
        assert alert.previous_price is None
        d = alert.to_dict()
        assert d["previous_price"] is None
        restored = AlertEvent.from_dict(d)
        assert restored.previous_price is None

    def test_reason_values(self) -> None:
        valid_reasons = ["price_drop", "below_target", "back_in_stock"]
        for reason in valid_reasons:
            alert = AlertEvent(
                product_sku="SKU",
                product_name="Name",
                store="amazon",
                price=800.00,
                target_price=899.00,
                url="https://example.com",
                timestamp="2025-01-01T00:00:00+00:00",
                reason=reason,
            )
            assert alert.reason == reason

    def test_price_coercion_from_dict(self) -> None:
        d = {
            "product_sku": "SKU",
            "product_name": "Name",
            "store": "amazon",
            "price": "1049.99",  # string
            "target_price": "1099.00",  # string
            "url": "https://example.com",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "reason": "below_target",
            "previous_price": None,
        }
        alert = AlertEvent.from_dict(d)
        assert isinstance(alert.price, float)
        assert alert.price == 1049.99
