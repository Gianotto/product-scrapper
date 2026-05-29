# Adding a New Store

Step-by-step guide to adding a 6th store to the price monitor.

---

## Overview

Adding a new store requires:

1. Creating a scraper class in `src/scrapers/`
2. Registering it in the scraper factory
3. Adding default config to `config.example.yaml`
4. Adding a search URL to the relevant products in `config.yaml`
5. Writing a test

---

## Step 1 — Create the scraper file

Create `src/scrapers/newstore.py` (replace `newstore` with the actual store slug,
e.g. `walmart`, `bhphotovideo`, `adorama`).

```python
"""Scraper for NewStore."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from src.models import PriceCheck, Product
from src.scrapers.base import BaseScraper


class NewStoreScraper(BaseScraper):
    """Scraper for NewStore."""

    name = "newstore"  # must match the key used in config.yaml stores section

    def _get_html(self, url: str) -> str:
        """Fetch a page and return HTML. Retries up to 3 times on network errors."""
        ua = UserAgent()
        headers = {
            "User-Agent": ua.random,
            "Accept-Language": "en-US,en;q=0.9",
        }
        timeout = getattr(self.general_config, "request_timeout_seconds", 30)

        @retry(
            stop=stop_after_attempt(getattr(self.general_config, "max_retries", 3)),
            wait=wait_fixed(getattr(self.general_config, "retry_backoff_seconds", 5)),
            retry=retry_if_exception_type(requests.exceptions.RequestException),
            reraise=True,
        )
        def _fetch() -> str:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.text

        return _fetch()

    def _parse_card(self, card) -> dict | None:
        """Extract product info from a single result card element.

        Returns a dict with keys: title, price, url, in_stock
        Returns None if the card cannot be parsed.
        """
        # TODO: inspect the store's HTML and update these selectors
        try:
            title_el = card.select_one(".product-title, h2.title, [data-testid='title']")
            price_el = card.select_one(".price, [data-price], .product-price")
            link_el = card.select_one("a[href]")

            if title_el is None:
                return None

            title = title_el.get_text(strip=True)

            price: float | None = None
            if price_el:
                import re
                raw = price_el.get_text(strip=True)
                match = re.search(r"[\d,]+\.?\d*", raw.replace(",", ""))
                if match:
                    price = float(match.group())

            url = ""
            if link_el:
                href = link_el.get("href", "")
                url = href if href.startswith("http") else f"https://www.newstore.com{href}"

            in_stock = True  # adjust based on actual out-of-stock indicators

            return {
                "title": title,
                "price": price,
                "url": url,
                "in_stock": in_stock,
            }
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to parse card: {exc}", exc=exc)
            return None

    def search(self, product: Product, search_url: str) -> list[PriceCheck]:
        """Search NewStore for *product* at *search_url*."""
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            html = self._get_html(search_url)
        except Exception as exc:
            logger.error(
                "NewStore fetch failed for {sku}: {exc}",
                sku=product.sku,
                exc=exc,
            )
            return [
                PriceCheck(
                    product_sku=product.sku,
                    store=self.name,
                    timestamp=timestamp,
                    success=False,
                    error=str(exc),
                )
            ]

        soup = BeautifulSoup(html, "lxml")

        # TODO: update this selector to match NewStore's result card container
        cards = soup.select(".product-card, .search-result-item, [data-testid='product']")

        if not cards:
            logger.warning(
                "NewStore: no product cards found for {sku} — HTML may have changed",
                sku=product.sku,
            )

        raw_results = [r for c in cards if (r := self._parse_card(c)) is not None]
        filtered = self.filter_results(raw_results, product)

        checks: list[PriceCheck] = []
        for item in filtered:
            checks.append(
                PriceCheck(
                    product_sku=product.sku,
                    store=self.name,
                    timestamp=timestamp,
                    success=True,
                    price=item.get("price"),
                    url=item.get("url"),
                    in_stock=bool(item.get("in_stock")),
                    raw_title=item.get("title"),
                )
            )

        return checks
```

---

## Step 2 — Register in the factory

Open `src/scrapers/__init__.py` and add the new scraper to the `_registry` dict:

```python
# Add this import inside get_scraper():
from src.scrapers.newstore import NewStoreScraper

# Add to the registry dict:
_registry: dict[str, type[BaseScraper]] = {
    "bestbuy": BestBuyScraper,
    "asus_shop": ASUSShopScraper,
    "newegg": NeweggScraper,
    "ebay": EbayScraper,
    "amazon": AmazonScraper,
    "newstore": NewStoreScraper,   # <-- add this line
}
```

---

## Step 3 — Add default config to `config.example.yaml`

Under the `stores:` section, add:

```yaml
stores:
  # ... existing stores ...

  newstore:
    enabled: true
    rate_limit_seconds: 3
```

---

## Step 4 — Add search URLs to products in `config.yaml`

For each product you want to monitor at the new store, add a `newstore:` URL entry
under the product's `stores:` section:

```yaml
products:
  - sku: "UX3405CA-PS99T"
    # ...
    stores:
      bestbuy: "https://..."
      amazon: "https://..."
      newstore: "https://www.newstore.com/search?q=UX3405CA-PS99T"   # <-- add
```

---

## Step 5 — Create an HTML fixture and test

1. Manually search for a product on the new store's website and save the HTML:

   ```bash
   curl -A "Mozilla/5.0 ..." "https://www.newstore.com/search?q=UX3405CA-PS99T" \
     > tests/fixtures/newstore_results.html
   ```

2. Create `tests/scrapers/test_newstore.py`:

   ```python
   from pathlib import Path
   import pytest
   from src.scrapers.newstore import NewStoreScraper
   from src.models import Product
   from tests.conftest import make_config   # or however your test helpers work

   FIXTURE = Path("tests/fixtures/newstore_results.html").read_text(encoding="utf-8")

   PRODUCT = Product(
       sku="UX3405CA-PS99T",
       name="ASUS Zenbook 14 OLED",
       target_price=1099.00,
       must_have_terms=["120Hz", "32GB"],
       blocklist_terms=["Refurbished", "60Hz"],
       stores={"newstore": "https://www.newstore.com/search?q=UX3405CA-PS99T"},
   )

   def test_parse_returns_results(requests_mock):
       requests_mock.get(
           "https://www.newstore.com/search?q=UX3405CA-PS99T",
           text=FIXTURE,
       )
       config = make_config()
       scraper = NewStoreScraper(config.stores["newstore"], config.general)
       results = scraper.search(PRODUCT, "https://www.newstore.com/search?q=UX3405CA-PS99T")

       assert len(results) > 0
       assert results[0].success is True
       assert results[0].price is not None

   def test_network_error_returns_failed_check(requests_mock):
       import requests
       requests_mock.get(
           "https://www.newstore.com/search?q=UX3405CA-PS99T",
           exc=requests.exceptions.Timeout,
       )
       config = make_config()
       scraper = NewStoreScraper(config.stores["newstore"], config.general)
       results = scraper.search(PRODUCT, "https://www.newstore.com/search?q=UX3405CA-PS99T")

       assert len(results) == 1
       assert results[0].success is False
       assert results[0].error is not None
   ```

---

## Step 6 — Run tests

```bash
.venv/bin/python -m pytest tests/ -v
```

All 155+ tests should still pass.

---

## Quick test on a real product

```bash
.venv/bin/python monitor.py --store newstore --product UX3405CA-PS99T --dry-run --verbose
```

Check the output to verify the scraper is finding the correct product with the
right price and stock status.
