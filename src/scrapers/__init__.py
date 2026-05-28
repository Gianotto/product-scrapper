# Scrapers package

from __future__ import annotations

from src.scrapers.base import BaseScraper, pick_best_result


def get_scraper(store_name: str, config) -> BaseScraper:
    """Factory function returning the right scraper for a store.

    Parameters
    ----------
    store_name:
        The store key as it appears in config.yaml (e.g. ``"bestbuy"``).
    config:
        AppConfig instance.

    Raises
    ------
    ValueError
        If no scraper is implemented for *store_name*.
    """
    from src.scrapers.bestbuy import BestBuyScraper

    # Additional scrapers will be registered here in Task 3
    _registry: dict[str, type[BaseScraper]] = {
        "bestbuy": BestBuyScraper,
    }

    if store_name not in _registry:
        raise ValueError(f"No scraper implemented for store: {store_name!r}")

    store_config = config.stores.get(store_name, {})
    return _registry[store_name](store_config, config.general)


__all__ = ["BaseScraper", "pick_best_result", "get_scraper"]
