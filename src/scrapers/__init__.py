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
    from src.scrapers.amazon import AmazonScraper
    from src.scrapers.asus_shop import ASUSShopScraper
    from src.scrapers.bestbuy import BestBuyScraper
    from src.scrapers.ebay import EbayScraper
    from src.scrapers.newegg import NeweggScraper

    _registry: dict[str, type[BaseScraper]] = {
        "bestbuy": BestBuyScraper,
        "asus_shop": ASUSShopScraper,
        "newegg": NeweggScraper,
        "ebay": EbayScraper,
        "amazon": AmazonScraper,
    }

    if store_name not in _registry:
        raise ValueError(f"No scraper implemented for store: {store_name!r}")

    store_config = config.stores.get(store_name, {})
    return _registry[store_name](store_config, config.general)


__all__ = ["BaseScraper", "pick_best_result", "get_scraper"]
