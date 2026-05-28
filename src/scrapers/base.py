"""
Abstract base class for all store scrapers.

Each concrete scraper implements `search()` and returns a list of PriceCheck
objects.  Filtering by must_have / blocklist terms is provided here and called
from within `search()`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import PriceCheck, Product


class BaseScraper(ABC):
    """Abstract scraper.  Subclasses must define ``name`` and implement ``search``."""

    name: str  # store name, e.g. "bestbuy"

    def __init__(self, config, general_config) -> None:
        """
        Parameters
        ----------
        config:
            StoreConfig for this store.
        general_config:
            GeneralConfig shared across all scrapers.
        """
        self.config = config
        self.general_config = general_config

    @abstractmethod
    def search(self, product: Product, search_url: str) -> list[PriceCheck]:
        """Search for *product* at *search_url* and return matched PriceCheck results.

        Implementations should:
        1. Fetch the page.
        2. Parse raw result dicts (at minimum containing a ``title`` key).
        3. Call ``self.filter_results(raw_dicts, product)`` to apply term filters.
        4. Convert survivors to PriceCheck objects and return them.
        """
        ...

    def filter_results(
        self, results: list[dict], product: Product
    ) -> list[dict]:
        """Apply must_have_terms and blocklist_terms filters to raw result dicts.

        Matching is case-insensitive against the ``title`` key of each dict.

        A result is kept when:
        - ALL must_have_terms are found in the title, AND
        - NO blocklist_terms are found in the title.

        Parameters
        ----------
        results:
            List of raw dicts, each expected to have a ``"title"`` key.
        product:
            Product whose filter terms should be applied.

        Returns
        -------
        list[dict]
            Filtered subset of *results*.
        """
        filtered: list[dict] = []
        for item in results:
            title_lower = (item.get("title") or "").lower()

            # Must-have check
            if not all(
                term.lower() in title_lower for term in product.must_have_terms
            ):
                continue

            # Blocklist check
            if any(term.lower() in title_lower for term in product.blocklist_terms):
                continue

            filtered.append(item)

        return filtered


# ---------------------------------------------------------------------------
# Free helper
# ---------------------------------------------------------------------------


def pick_best_result(checks: list[PriceCheck]) -> PriceCheck | None:
    """Return the best result from a list of PriceCheck objects.

    Preference order:
    1. Cheapest in-stock result (price is not None).
    2. Cheapest result overall if nothing is in-stock.
    3. None if *checks* is empty.
    """
    if not checks:
        return None

    in_stock = [c for c in checks if c.in_stock and c.price is not None]
    if in_stock:
        return min(in_stock, key=lambda c: c.price)  # type: ignore[return-value]

    with_price = [c for c in checks if c.price is not None]
    if with_price:
        return min(with_price, key=lambda c: c.price)  # type: ignore[return-value]

    # All checks have no price — return first
    return checks[0]
