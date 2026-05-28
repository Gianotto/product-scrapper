"""
Integration tests for src/orchestrator.py.

All external I/O (storage, alerts, scrapers) is mocked so no network calls
or filesystem writes happen during the test run.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import load_config
from src.models import AlertEvent, PriceCheck, Product
from src.orchestrator import check_and_alert, run_all_checks

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def test_config():
    """Load the minimal test config from tests/fixtures/test_config.yaml."""
    return load_config(FIXTURES_DIR / "test_config.yaml", env_path=".env.nonexistent")


@pytest.fixture()
def product() -> Product:
    return Product(
        sku="TEST-SKU-001",
        name="Test Laptop",
        target_price=1000.00,
        must_have_terms=["120Hz"],
        blocklist_terms=["60Hz"],
        stores={"bestbuy": "https://www.bestbuy.com/search?q=test"},
    )


def _make_check(
    price: float | None = 900.00,
    in_stock: bool = True,
    store: str = "bestbuy",
    sku: str = "TEST-SKU-001",
    timestamp: str | None = None,
) -> PriceCheck:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    return PriceCheck(
        product_sku=sku,
        store=store,
        timestamp=timestamp,
        success=True,
        price=price,
        url="https://www.bestbuy.com/site/test",
        in_stock=in_stock,
    )


def _make_alert_event(
    reason: str = "below_target",
    store: str = "bestbuy",
    sku: str = "TEST-SKU-001",
    timestamp: str | None = None,
) -> AlertEvent:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    return AlertEvent(
        product_sku=sku,
        product_name="Test Laptop",
        store=store,
        price=900.00,
        target_price=1000.00,
        url="https://www.bestbuy.com/site/test",
        timestamp=timestamp,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# TestBelowTargetTrigger
# ---------------------------------------------------------------------------


class TestBelowTargetTrigger:
    """Verify the below_target alert trigger fires correctly."""

    def test_below_target_sends_alert(self, test_config, product: Product) -> None:
        """price < target_price and no recent alert → send_alert called once."""
        check = _make_check(price=900.00)  # 900 < 1000

        with (
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=None),
            patch("src.orchestrator.storage.append_alert") as mock_append,
            patch("src.orchestrator.alerts.send_alert", return_value=True) as mock_send,
        ):
            result = check_and_alert(check, product, test_config)

        assert result is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        event: AlertEvent = call_args[0][0]
        assert event.reason == "below_target"
        mock_append.assert_called_once()

    def test_at_target_sends_alert(self, test_config, product: Product) -> None:
        """price == target_price → alert fires (edge case: price <= target)."""
        check = _make_check(price=1000.00)  # exactly at target

        with (
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=None),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True) as mock_send,
        ):
            result = check_and_alert(check, product, test_config)

        assert result is True
        reasons = [call[0][0].reason for call in mock_send.call_args_list]
        assert "below_target" in reasons

    def test_above_target_no_alert(self, test_config, product: Product) -> None:
        """price > target_price → send_alert NOT called for below_target."""
        check = _make_check(price=1100.00)  # above target

        with (
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=None),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True) as mock_send,
        ):
            result = check_and_alert(check, product, test_config)

        assert result is False
        mock_send.assert_not_called()

    def test_cooldown_prevents_duplicate_alert(
        self, test_config, product: Product
    ) -> None:
        """A recent below_target alert for the same store prevents a new one."""
        check = _make_check(price=900.00)
        recent = _make_alert_event(reason="below_target", store="bestbuy")

        with (
            patch(
                "src.orchestrator.storage.get_alerts_sent", return_value=[recent]
            ),
            patch("src.orchestrator.storage.get_last_check", return_value=None),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True) as mock_send,
        ):
            result = check_and_alert(check, product, test_config)

        assert result is False
        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# TestPriceDropTrigger
# ---------------------------------------------------------------------------


class TestPriceDropTrigger:
    """Verify the price_drop alert trigger fires at the configured threshold."""

    def test_price_drop_above_threshold_sends_alert(
        self, test_config, product: Product
    ) -> None:
        """$1299 → $1200 = ~7.6% drop, threshold is 5% → alert fires."""
        last = _make_check(price=1299.00, in_stock=True)
        current = _make_check(price=1200.00, in_stock=True)

        with (
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=last),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True) as mock_send,
        ):
            result = check_and_alert(current, product, test_config)

        assert result is True
        reasons = [call[0][0].reason for call in mock_send.call_args_list]
        assert "price_drop" in reasons
        # Verify previous_price is set correctly
        pd_call = next(c for c in mock_send.call_args_list if c[0][0].reason == "price_drop")
        assert pd_call[0][0].previous_price == 1299.00

    def test_price_drop_below_threshold_no_alert(
        self, test_config, product: Product
    ) -> None:
        """$1299 → $1260 = ~3% drop, threshold is 5% → NO alert fires."""
        last = _make_check(price=1299.00, in_stock=True)
        current = _make_check(price=1260.00, in_stock=True)

        with (
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=last),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True) as mock_send,
        ):
            result = check_and_alert(current, product, test_config)

        assert result is False
        reasons = [call[0][0].reason for call in mock_send.call_args_list]
        assert "price_drop" not in reasons

    def test_no_previous_check_no_price_drop_alert(
        self, test_config, product: Product
    ) -> None:
        """First check ever (no previous data) → no price_drop alert."""
        check = _make_check(price=900.00)

        with (
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=None),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True) as mock_send,
        ):
            # price is below target so below_target fires, but price_drop should NOT
            check_and_alert(check, product, test_config)

        reasons = [call[0][0].reason for call in mock_send.call_args_list]
        assert "price_drop" not in reasons

    def test_price_drop_cooldown_prevents_duplicate(
        self, test_config, product: Product
    ) -> None:
        """A recent price_drop alert for the same store prevents a new one."""
        last = _make_check(price=1299.00, in_stock=True)
        current = _make_check(price=1100.00, in_stock=True)  # >5% drop
        recent = _make_alert_event(reason="price_drop", store="bestbuy")

        with (
            patch(
                "src.orchestrator.storage.get_alerts_sent", return_value=[recent]
            ),
            patch("src.orchestrator.storage.get_last_check", return_value=last),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True) as mock_send,
        ):
            check_and_alert(current, product, test_config)

        reasons = [call[0][0].reason for call in mock_send.call_args_list]
        assert "price_drop" not in reasons


# ---------------------------------------------------------------------------
# TestBackInStockTrigger
# ---------------------------------------------------------------------------


class TestBackInStockTrigger:
    """Verify the back_in_stock alert trigger fires on stock transition."""

    def test_back_in_stock_sends_alert(self, test_config, product: Product) -> None:
        """last check out of stock, current check in stock → alert fires."""
        last = _make_check(price=1099.00, in_stock=False)
        current = _make_check(price=1099.00, in_stock=True)

        with (
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=last),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True) as mock_send,
        ):
            result = check_and_alert(current, product, test_config)

        assert result is True
        reasons = [call[0][0].reason for call in mock_send.call_args_list]
        assert "back_in_stock" in reasons

    def test_was_in_stock_no_alert(self, test_config, product: Product) -> None:
        """last check already in stock → no back_in_stock alert."""
        last = _make_check(price=1099.00, in_stock=True)
        current = _make_check(price=1099.00, in_stock=True)

        with (
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=last),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True) as mock_send,
        ):
            check_and_alert(current, product, test_config)

        reasons = [call[0][0].reason for call in mock_send.call_args_list]
        assert "back_in_stock" not in reasons

    def test_still_out_of_stock_no_alert(self, test_config, product: Product) -> None:
        """last check out of stock, current still out of stock → no alert."""
        last = _make_check(price=None, in_stock=False)
        current = _make_check(price=None, in_stock=False)

        with (
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=last),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True) as mock_send,
        ):
            # price is None → check_and_alert returns early without any alert
            result = check_and_alert(current, product, test_config)

        assert result is False
        mock_send.assert_not_called()

    def test_back_in_stock_cooldown_prevents_duplicate(
        self, test_config, product: Product
    ) -> None:
        """A recent back_in_stock alert prevents a duplicate."""
        last = _make_check(price=1099.00, in_stock=False)
        current = _make_check(price=1099.00, in_stock=True)
        recent = _make_alert_event(reason="back_in_stock", store="bestbuy")

        with (
            patch(
                "src.orchestrator.storage.get_alerts_sent", return_value=[recent]
            ),
            patch("src.orchestrator.storage.get_last_check", return_value=last),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True) as mock_send,
        ):
            check_and_alert(current, product, test_config)

        reasons = [call[0][0].reason for call in mock_send.call_args_list]
        assert "back_in_stock" not in reasons


# ---------------------------------------------------------------------------
# TestCooldownUsesConfigValue
# ---------------------------------------------------------------------------


class TestCooldownUsesConfigValue:
    """Verify the cooldown reads from config, not a hardcoded value."""

    def test_cooldown_minutes_passed_to_storage(
        self, test_config, product: Product
    ) -> None:
        """storage.get_alerts_sent should be called with cooldown_hours derived from config."""
        check = _make_check(price=900.00)
        expected_hours = test_config.alerts.cooldown_minutes / 60  # 360 / 60 = 6.0

        with (
            patch(
                "src.orchestrator.storage.get_alerts_sent", return_value=[]
            ) as mock_get,
            patch("src.orchestrator.storage.get_last_check", return_value=None),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True),
        ):
            check_and_alert(check, product, test_config)

        mock_get.assert_called_once_with(product.sku, hours=expected_hours)


# ---------------------------------------------------------------------------
# TestRunAllChecks
# ---------------------------------------------------------------------------


class TestRunAllChecks:
    """Integration tests for the run_all_checks() main loop."""

    def _make_price_check_result(self) -> list[PriceCheck]:
        return [
            PriceCheck(
                product_sku="TEST-SKU-001",
                store="bestbuy",
                timestamp=datetime.now(timezone.utc).isoformat(),
                success=True,
                price=899.00,
                url="https://www.bestbuy.com/site/test",
                in_stock=True,
                raw_title="Test Laptop 120Hz",
                matched_terms=["120Hz"],
            )
        ]

    def test_dry_run_does_not_save_or_alert(self, test_config) -> None:
        """dry_run=True → append_check and append_alert NOT called (no disk writes).

        send_alert IS called in dry_run mode (it only logs, does no HTTP), but
        storage writes are suppressed entirely.
        """
        results = self._make_price_check_result()

        with (
            patch(
                "src.orchestrator.get_scraper"
            ) as mock_get_scraper,
            patch("src.orchestrator.storage.append_check") as mock_append_check,
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=None),
            patch("src.orchestrator.storage.append_alert") as mock_append_alert,
            patch(
                "src.orchestrator.alerts.send_alert", return_value=True
            ) as mock_send_alert,
        ):
            mock_scraper = MagicMock()
            mock_scraper.search.return_value = results
            mock_get_scraper.return_value = mock_scraper

            stats = run_all_checks(test_config, dry_run=True)

        assert stats.successful_checks == 1
        # Storage writes must be suppressed in dry_run
        mock_append_check.assert_not_called()
        mock_append_alert.assert_not_called()
        # send_alert is called (logs what would happen) but with dry_run=True
        mock_send_alert.assert_called_once()
        call_kwargs = mock_send_alert.call_args[1]
        assert call_kwargs.get("dry_run") is True

    def test_store_filter_only_checks_selected_store(self, test_config) -> None:
        """store_filter='bestbuy' → only bestbuy scraper is instantiated."""
        results = self._make_price_check_result()

        with (
            patch(
                "src.orchestrator.get_scraper"
            ) as mock_get_scraper,
            patch("src.orchestrator.storage.append_check"),
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=None),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=False),
            patch("src.orchestrator.storage.update_last_run"),
            patch("src.orchestrator.storage.acquire_lock", return_value=True),
            patch("src.orchestrator.storage.release_lock"),
            patch("src.orchestrator.storage.rotate_if_needed"),
        ):
            mock_scraper = MagicMock()
            mock_scraper.search.return_value = results
            mock_get_scraper.return_value = mock_scraper

            run_all_checks(test_config, dry_run=False, store_filter="bestbuy")

        # get_scraper should have been called exactly once with "bestbuy"
        assert mock_get_scraper.call_count == 1
        assert mock_get_scraper.call_args[0][0] == "bestbuy"

    def test_store_filter_skips_other_stores(self, test_config) -> None:
        """store_filter='amazon' → bestbuy scraper is never called (product only has bestbuy)."""
        with (
            patch(
                "src.orchestrator.get_scraper"
            ) as mock_get_scraper,
            patch("src.orchestrator.storage.acquire_lock", return_value=True),
            patch("src.orchestrator.storage.release_lock"),
            patch("src.orchestrator.storage.rotate_if_needed"),
            patch("src.orchestrator.storage.update_last_run"),
        ):
            stats = run_all_checks(
                test_config, dry_run=False, store_filter="amazon"
            )

        mock_get_scraper.assert_not_called()
        assert stats.stores_checked == 0

    def test_scraper_failure_does_not_abort_loop(self, test_config) -> None:
        """Scraper raises exception → failed_checks incremented, loop continues."""
        with (
            patch(
                "src.orchestrator.get_scraper"
            ) as mock_get_scraper,
            patch("src.orchestrator.storage.append_check"),
            patch("src.orchestrator.storage.update_last_run"),
            patch("src.orchestrator.storage.acquire_lock", return_value=True),
            patch("src.orchestrator.storage.release_lock"),
            patch("src.orchestrator.storage.rotate_if_needed"),
        ):
            mock_scraper = MagicMock()
            mock_scraper.search.side_effect = RuntimeError("Scraper blew up")
            mock_get_scraper.return_value = mock_scraper

            stats = run_all_checks(test_config, dry_run=False)

        assert stats.failed_checks == 1
        assert stats.successful_checks == 0
        # Loop did not raise — test completes normally

    def test_no_results_records_failed_check(self, test_config) -> None:
        """Scraper returns [] → failed_checks incremented."""
        with (
            patch(
                "src.orchestrator.get_scraper"
            ) as mock_get_scraper,
            patch("src.orchestrator.storage.append_check"),
            patch("src.orchestrator.storage.update_last_run"),
            patch("src.orchestrator.storage.acquire_lock", return_value=True),
            patch("src.orchestrator.storage.release_lock"),
            patch("src.orchestrator.storage.rotate_if_needed"),
        ):
            mock_scraper = MagicMock()
            mock_scraper.search.return_value = []
            mock_get_scraper.return_value = mock_scraper

            stats = run_all_checks(test_config, dry_run=False)

        assert stats.failed_checks == 1
        assert stats.successful_checks == 0

    def test_successful_check_increments_counter(self, test_config) -> None:
        """Scraper returns a valid result → successful_checks incremented."""
        results = self._make_price_check_result()

        with (
            patch(
                "src.orchestrator.get_scraper"
            ) as mock_get_scraper,
            patch("src.orchestrator.storage.append_check"),
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=None),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=False),
            patch("src.orchestrator.storage.update_last_run"),
            patch("src.orchestrator.storage.acquire_lock", return_value=True),
            patch("src.orchestrator.storage.release_lock"),
            patch("src.orchestrator.storage.rotate_if_needed"),
        ):
            mock_scraper = MagicMock()
            mock_scraper.search.return_value = results
            mock_get_scraper.return_value = mock_scraper

            stats = run_all_checks(test_config, dry_run=False)

        assert stats.successful_checks == 1
        assert stats.failed_checks == 0
        assert stats.products_checked == 1
        assert stats.stores_checked == 1

    def test_alerts_sent_counter_incremented_on_alert(self, test_config) -> None:
        """When check_and_alert returns True, stats.alerts_sent is incremented."""
        results = self._make_price_check_result()
        # price=899 < target=1000, no cooldown → below_target fires

        with (
            patch(
                "src.orchestrator.get_scraper"
            ) as mock_get_scraper,
            patch("src.orchestrator.storage.append_check"),
            patch("src.orchestrator.storage.get_alerts_sent", return_value=[]),
            patch("src.orchestrator.storage.get_last_check", return_value=None),
            patch("src.orchestrator.storage.append_alert"),
            patch("src.orchestrator.alerts.send_alert", return_value=True),
            patch("src.orchestrator.storage.update_last_run"),
            patch("src.orchestrator.storage.acquire_lock", return_value=True),
            patch("src.orchestrator.storage.release_lock"),
            patch("src.orchestrator.storage.rotate_if_needed"),
        ):
            mock_scraper = MagicMock()
            mock_scraper.search.return_value = results
            mock_get_scraper.return_value = mock_scraper

            stats = run_all_checks(test_config, dry_run=False)

        assert stats.alerts_sent == 1

    def test_lock_not_acquired_returns_empty_stats(self, test_config) -> None:
        """If lock acquisition fails, the function returns immediately with zero counts."""
        with patch(
            "src.orchestrator.storage.acquire_lock", return_value=False
        ):
            stats = run_all_checks(test_config, dry_run=False)

        assert stats.products_checked == 0
        assert stats.stores_checked == 0
        assert stats.successful_checks == 0
        assert stats.failed_checks == 0
