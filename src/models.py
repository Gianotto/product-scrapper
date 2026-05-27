"""
Data models for the price monitor application.

All models use Python 3.11+ type hints and are based on dataclasses.
Timestamps are ISO 8601 UTC strings throughout.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Product:
    """Represents a monitored product with its target price and store URLs."""

    sku: str
    name: str
    target_price: float
    must_have_terms: list[str]
    blocklist_terms: list[str]
    stores: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Product:
        return cls(
            sku=data["sku"],
            name=data["name"],
            target_price=float(data["target_price"]),
            must_have_terms=list(data.get("must_have_terms", [])),
            blocklist_terms=list(data.get("blocklist_terms", [])),
            stores=dict(data.get("stores", {})),
        )


@dataclass
class PriceCheck:
    """
    Records the result of a single price check for one product on one store.

    success=True means the scrape completed without error (price may still be None
    if the item was not found or out of stock).
    """

    product_sku: str
    store: str
    timestamp: str  # ISO 8601 UTC
    success: bool
    price: float | None = None
    url: str | None = None
    in_stock: bool = False
    raw_title: str | None = None
    matched_terms: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PriceCheck:
        return cls(
            product_sku=data["product_sku"],
            store=data["store"],
            timestamp=data["timestamp"],
            success=bool(data["success"]),
            price=float(data["price"]) if data.get("price") is not None else None,
            url=data.get("url"),
            in_stock=bool(data.get("in_stock", False)),
            raw_title=data.get("raw_title"),
            matched_terms=list(data.get("matched_terms", [])),
            error=data.get("error"),
        )


@dataclass
class AlertEvent:
    """
    Records a price-alert notification that was (or will be) sent via the webhook.

    reason values: "price_drop" | "below_target" | "back_in_stock"
    """

    product_sku: str
    product_name: str
    store: str
    price: float
    target_price: float
    url: str
    timestamp: str  # ISO 8601 UTC
    reason: str  # "price_drop" | "below_target" | "back_in_stock"
    previous_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertEvent:
        return cls(
            product_sku=data["product_sku"],
            product_name=data["product_name"],
            store=data["store"],
            price=float(data["price"]),
            target_price=float(data["target_price"]),
            url=data["url"],
            timestamp=data["timestamp"],
            reason=data["reason"],
            previous_price=(
                float(data["previous_price"])
                if data.get("previous_price") is not None
                else None
            ),
        )
