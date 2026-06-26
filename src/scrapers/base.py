"""
Abstract base class for all store scrapers.

Each concrete scraper implements `search()` and returns a list of PriceCheck
objects.  Filtering by must_have / blocklist terms is provided here and called
from within `search()`.  Common HTTP infrastructure (browser headers, session,
retry logic, debug HTML dumps) lives here so scrapers share one implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed

from src.models import PriceCheck, Product

_DEBUG_MAX_BYTES = 1 * 1024 * 1024


class BaseScraper(ABC):
    """Abstract scraper.  Subclasses must define ``name`` and implement ``search``."""

    name: str
    _referer: str = ""
    _debug_html_name: str = "debug.html"

    def __init__(self, config, general_config) -> None:
        self.config = config
        self.general_config = general_config
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # HTTP helpers — shared by all scrapers
    # ------------------------------------------------------------------

    def _get_user_agent(self) -> str:
        if getattr(self.general_config, "user_agents_rotation", True):
            try:
                from fake_useragent import UserAgent

                return UserAgent().chrome
            except Exception:
                pass
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )

    def _browser_headers(self) -> dict[str, str]:
        """Return a full set of browser-like request headers including Sec-* hints."""
        headers: dict[str, str] = {
            "User-Agent": self._get_user_agent(),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,image/apng,*/*;"
                "q=0.8,application/signed-exchange;v=b3;q=0.7"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        if self._referer:
            headers["Referer"] = self._referer
            headers["Sec-Fetch-Site"] = "same-origin"
        return headers

    def _fetch_with_config(self, url: str) -> requests.Response:
        """Fetch *url* with retry settings from general_config."""
        max_retries = getattr(self.general_config, "max_retries", 3)
        backoff = getattr(self.general_config, "retry_backoff_seconds", 5)
        timeout = getattr(self.general_config, "request_timeout_seconds", 30)

        fetch_fn = retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_fixed(backoff),
            reraise=True,
        )(self._do_get)

        return fetch_fn(url, timeout)

    def _do_get(self, url: str, timeout: int) -> requests.Response:
        return self._session.get(
            url,
            headers=self._browser_headers(),
            timeout=timeout,
            allow_redirects=True,
        )

    def _dump_debug_html(self, html: str) -> None:
        """Write HTML to logs/<_debug_html_name> (max 1 MB) for debugging."""
        try:
            logs_dir = Path("logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
            debug_path = logs_dir / self._debug_html_name
            content = html.encode("utf-8", errors="replace")[:_DEBUG_MAX_BYTES]
            debug_path.write_bytes(content)
            logger.debug("Debug HTML written to {path}", path=debug_path)
        except Exception as exc:
            logger.debug("Could not write debug HTML: {exc}", exc=exc)

    def _select_first(self, tag: Any, selectors: list[str]) -> Any | None:
        """Try each CSS selector in order and return the first match, or None."""
        for sel in selectors:
            result = tag.select_one(sel)
            if result:
                return result
        return None

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

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

    def filter_results(self, results: list[dict], product: Product) -> list[dict]:
        """Apply must_have_terms and blocklist_terms filters to raw result dicts.

        Matching is case-insensitive against the ``title`` key of each dict.

        A result is kept when:
        - ALL must_have_terms are found in the title, AND
        - NO blocklist_terms are found in the title.
        """
        filtered: list[dict] = []
        for item in results:
            title_lower = (item.get("title") or "").lower()

            if not all(term.lower() in title_lower for term in product.must_have_terms):
                continue

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
        return min(in_stock, key=lambda c: c.price)  # type: ignore[arg-type,return-value]

    with_price = [c for c in checks if c.price is not None]
    if with_price:
        return min(with_price, key=lambda c: c.price)  # type: ignore[arg-type,return-value]

    return checks[0]
