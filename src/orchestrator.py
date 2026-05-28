"""
Main execution loop for the price monitor.

Iterates over all configured products and stores, runs the appropriate scraper,
evaluates alert triggers, and persists results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from src import alerts, storage
from src.config import AppConfig
from src.models import AlertEvent, PriceCheck, Product
from src.scrapers import get_scraper
from src.scrapers.base import pick_best_result


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@dataclass
class RunStats:
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    products_checked: int = 0
    stores_checked: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    alerts_sent: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Alert decision logic
# ---------------------------------------------------------------------------


def check_and_alert(
    check: PriceCheck,
    product: Product,
    config: AppConfig,
    dry_run: bool = False,
) -> bool:
    """Evaluate alert triggers for *check* and send alerts where appropriate.

    Returns True if at least one alert was sent.
    """
    if check.price is None:
        return False

    webhook_url = config.alerts.webhook_url
    cooldown_hours = config.alerts.cooldown_minutes / 60
    triggers = config.alerts.triggers
    timestamp = datetime.now(timezone.utc).isoformat()

    sent_any = False

    # Retrieve recent alerts for this SKU (used by cooldown checks)
    try:
        recent_alerts = storage.get_alerts_sent(product.sku, hours=cooldown_hours)
    except Exception as exc:
        logger.warning("Could not read recent alerts for {sku}: {exc}", sku=product.sku, exc=exc)
        recent_alerts = []

    def _was_recently_alerted(reason: str) -> bool:
        return any(
            a.reason == reason and a.store == check.store
            for a in recent_alerts
        )

    def _send(reason: str, previous_price: float | None = None) -> None:
        nonlocal sent_any
        event = AlertEvent(
            product_sku=product.sku,
            product_name=product.name,
            store=check.store,
            price=check.price,  # type: ignore[arg-type]
            target_price=product.target_price,
            url=check.url or "",
            timestamp=timestamp,
            reason=reason,
            previous_price=previous_price,
        )
        result = alerts.send_alert(event, webhook_url, dry_run=dry_run)
        if result:
            if not dry_run:
                try:
                    storage.append_alert(event)
                except Exception as exc:
                    logger.error(
                        "Failed to persist alert for {sku}: {exc}",
                        sku=product.sku,
                        exc=exc,
                    )
            sent_any = True
            logger.info(
                "Alert fired [{reason}] for {sku} @ {store}: ${price:.2f}",
                reason=reason,
                sku=product.sku,
                store=check.store,
                price=check.price,
            )

    # --- Trigger 1: below_target ---
    if triggers.below_target and check.price <= product.target_price:
        if not _was_recently_alerted("below_target"):
            _send("below_target")

    # --- Trigger 2: price_drop ---
    last_check = None
    try:
        last_check = storage.get_last_check(product.sku, check.store)
    except Exception as exc:
        logger.warning(
            "Could not read last check for {sku}@{store}: {exc}",
            sku=product.sku,
            store=check.store,
            exc=exc,
        )

    if last_check is not None and last_check.price is not None:
        drop_pct = (last_check.price - check.price) / last_check.price * 100
        if drop_pct >= triggers.price_drop_percent:
            if not _was_recently_alerted("price_drop"):
                _send("price_drop", previous_price=last_check.price)

    # --- Trigger 3: back_in_stock ---
    if triggers.back_in_stock and check.in_stock:
        if last_check is not None and not last_check.in_stock:
            if not _was_recently_alerted("back_in_stock"):
                _send("back_in_stock")

    return sent_any


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_all_checks(
    config: AppConfig,
    dry_run: bool = False,
    store_filter: str | None = None,
    product_filter: str | None = None,
) -> RunStats:
    """Run price checks for all configured products and stores.

    Parameters
    ----------
    config:
        Loaded application configuration.
    dry_run:
        When True, skip saving to disk and skip sending real alerts.
    store_filter:
        If set, only check this store name.
    product_filter:
        If set, only check the product with this SKU.

    Returns
    -------
    RunStats
        Summary of the run.
    """
    stats = RunStats(started_at=datetime.now(timezone.utc).isoformat())
    start_ts = time.monotonic()

    if not dry_run:
        if not storage.acquire_lock():
            logger.error("Could not acquire lock — another instance may be running.")
            stats.completed_at = datetime.now(timezone.utc).isoformat()
            return stats

    try:
        if not dry_run:
            try:
                storage.rotate_if_needed()
            except Exception as exc:
                logger.warning("Log rotation failed: {exc}", exc=exc)

        for product in config.products:
            # Optional product filter
            if product_filter and product.sku != product_filter:
                continue

            stats.products_checked += 1

            for store_name, search_url in product.stores.items():
                # Optional store filter
                if store_filter and store_name != store_filter:
                    continue

                # Skip unknown stores
                if store_name not in config.stores:
                    logger.warning(
                        "Unknown store '{store}' for SKU={sku} — skipping",
                        store=store_name,
                        sku=product.sku,
                    )
                    continue

                # Skip disabled stores
                store_cfg = config.stores[store_name]
                if not store_cfg.enabled:
                    logger.debug(
                        "Store '{store}' is disabled — skipping",
                        store=store_name,
                    )
                    continue

                stats.stores_checked += 1
                logger.info(
                    "Checking {store} for SKU={sku}",
                    store=store_name,
                    sku=product.sku,
                )

                # Instantiate scraper
                try:
                    scraper = get_scraper(store_name, config)
                except ValueError as exc:
                    logger.warning(str(exc))
                    # Record failed check
                    failed_check = PriceCheck(
                        product_sku=product.sku,
                        store=store_name,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        success=False,
                        error=str(exc),
                    )
                    if not dry_run:
                        try:
                            storage.append_check(failed_check)
                        except Exception as save_exc:
                            logger.error("Failed to save check: {exc}", exc=save_exc)
                    stats.failed_checks += 1
                    continue

                # Run scraper
                try:
                    results = scraper.search(product, search_url)
                except Exception as exc:
                    logger.error(
                        "Scraper error for {store}/{sku}: {exc}",
                        store=store_name,
                        sku=product.sku,
                        exc=exc,
                    )
                    results = []

                best = pick_best_result(results)

                if best is None:
                    # No results — record failed check
                    failed_check = PriceCheck(
                        product_sku=product.sku,
                        store=store_name,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        success=False,
                        error="No matching results",
                    )
                    if not dry_run:
                        try:
                            storage.append_check(failed_check)
                        except Exception as save_exc:
                            logger.error("Failed to save check: {exc}", exc=save_exc)
                    stats.failed_checks += 1
                else:
                    stats.successful_checks += 1
                    if not dry_run:
                        try:
                            storage.append_check(best)
                        except Exception as save_exc:
                            logger.error("Failed to save check: {exc}", exc=save_exc)

                    # Evaluate alerts
                    try:
                        alerted = check_and_alert(best, product, config, dry_run)
                        if alerted:
                            stats.alerts_sent += 1
                    except Exception as exc:
                        logger.error(
                            "Alert evaluation error for {sku}@{store}: {exc}",
                            sku=product.sku,
                            store=store_name,
                            exc=exc,
                        )

                # Rate limiting (skip in dry_run for speed)
                if not dry_run:
                    rate_limit = store_cfg.rate_limit_seconds
                    if rate_limit > 0:
                        time.sleep(rate_limit)

        # Persist run summary
        stats.completed_at = datetime.now(timezone.utc).isoformat()
        stats.duration_seconds = round(time.monotonic() - start_ts, 2)

        if not dry_run:
            try:
                storage.update_last_run(stats.to_dict())
            except Exception as exc:
                logger.warning("Failed to write last_run.json: {exc}", exc=exc)

    finally:
        if not dry_run:
            storage.release_lock()

    return stats
