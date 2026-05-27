"""
Tests for src/storage.py.

All tests use pytest's tmp_path fixture to redirect DATA_DIR so they never
touch real data files.
"""

from __future__ import annotations

import gzip
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.models import AlertEvent, PriceCheck
from src.storage import (
    acquire_lock,
    append_alert,
    append_check,
    get_alerts_sent,
    get_last_check,
    load_log,
    release_lock,
    rotate_if_needed,
    save_log,
    update_last_run,
)


# ---------------------------------------------------------------------------
# Helper to redirect DATA_DIR to a temp directory for every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def use_tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point DATA_DIR to a fresh temp directory for each test."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    return data_dir


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_check(
    sku: str = "UX3405CA-PS99T",
    store: str = "bestbuy",
    price: float | None = 1049.99,
    success: bool = True,
    timestamp: str = "2025-05-27T10:00:00+00:00",
) -> PriceCheck:
    return PriceCheck(
        product_sku=sku,
        store=store,
        timestamp=timestamp,
        success=success,
        price=price,
        url="https://www.bestbuy.com/site/...",
        in_stock=price is not None,
    )


def _make_alert(
    sku: str = "UX3405CA-PS99T",
    store: str = "bestbuy",
    reason: str = "below_target",
    timestamp: str | None = None,
) -> AlertEvent:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    return AlertEvent(
        product_sku=sku,
        product_name="ASUS Zenbook 14 OLED",
        store=store,
        price=1049.99,
        target_price=1099.00,
        url="https://www.bestbuy.com/site/...",
        timestamp=timestamp,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# load_log / save_log
# ---------------------------------------------------------------------------


class TestLoadSaveLog:
    def test_load_creates_fresh_log_when_missing(self) -> None:
        log = load_log()
        assert log["version"] == "1.0"
        assert "created_at" in log
        assert log["products"] == {}

    def test_save_and_reload(self, use_tmp_data_dir: Path) -> None:
        log = load_log()
        log["products"]["TEST"] = {"checks": [], "alerts_sent": []}
        save_log(log)

        reloaded = load_log()
        assert "TEST" in reloaded["products"]

    def test_save_updates_last_updated(self, use_tmp_data_dir: Path) -> None:
        log = load_log()
        before = datetime.now(timezone.utc).isoformat()
        save_log(log)
        reloaded = load_log()
        assert reloaded["last_updated"] >= before

    def test_atomic_write_uses_tmp_then_replaces(
        self, use_tmp_data_dir: Path
    ) -> None:
        """Verify that a .tmp file is not left over after save_log."""
        log = load_log()
        save_log(log)

        price_log_path = use_tmp_data_dir / "price_log.json"
        tmp_path = price_log_path.with_suffix(".tmp")
        assert price_log_path.exists()
        assert not tmp_path.exists()


# ---------------------------------------------------------------------------
# append_check / get_last_check
# ---------------------------------------------------------------------------


class TestAppendCheckGetLastCheck:
    def test_append_creates_product_entry(self) -> None:
        check = _make_check()
        append_check(check)
        log = load_log()
        assert "UX3405CA-PS99T" in log["products"]
        assert len(log["products"]["UX3405CA-PS99T"]["checks"]) == 1

    def test_get_last_check_returns_none_when_no_data(self) -> None:
        result = get_last_check("MISSING-SKU", "bestbuy")
        assert result is None

    def test_get_last_check_returns_most_recent(self) -> None:
        check_old = _make_check(
            price=1100.00, timestamp="2025-05-27T08:00:00+00:00"
        )
        check_new = _make_check(
            price=1049.99, timestamp="2025-05-27T10:00:00+00:00"
        )
        append_check(check_old)
        append_check(check_new)

        result = get_last_check("UX3405CA-PS99T", "bestbuy")
        assert result is not None
        assert result.price == 1049.99

    def test_get_last_check_filters_by_store(self) -> None:
        check_bb = _make_check(store="bestbuy", price=1049.99)
        check_amz = _make_check(store="amazon", price=999.00)
        append_check(check_bb)
        append_check(check_amz)

        result = get_last_check("UX3405CA-PS99T", "amazon")
        assert result is not None
        assert result.price == 999.00

    def test_append_multiple_skus(self) -> None:
        check1 = _make_check(sku="SKU-A", store="bestbuy")
        check2 = _make_check(sku="SKU-B", store="amazon")
        append_check(check1)
        append_check(check2)

        assert get_last_check("SKU-A", "bestbuy") is not None
        assert get_last_check("SKU-B", "amazon") is not None
        assert get_last_check("SKU-A", "amazon") is None

    def test_check_roundtrip_preserves_fields(self) -> None:
        check = PriceCheck(
            product_sku="TEST-SKU",
            store="newegg",
            timestamp="2025-05-27T12:00:00+00:00",
            success=True,
            price=749.99,
            url="https://newegg.com/...",
            in_stock=True,
            raw_title="ASUS Zenbook 32GB",
            matched_terms=["120Hz", "32GB"],
            error=None,
        )
        append_check(check)
        restored = get_last_check("TEST-SKU", "newegg")
        assert restored is not None
        assert restored.raw_title == "ASUS Zenbook 32GB"
        assert restored.matched_terms == ["120Hz", "32GB"]


# ---------------------------------------------------------------------------
# append_alert / get_alerts_sent
# ---------------------------------------------------------------------------


class TestAlerts:
    def test_append_alert_creates_entry(self) -> None:
        alert = _make_alert()
        append_alert(alert)
        log = load_log()
        sku = alert.product_sku
        assert len(log["products"][sku]["alerts_sent"]) == 1

    def test_get_alerts_sent_returns_recent(self) -> None:
        alert = _make_alert()  # timestamp = now
        append_alert(alert)
        results = get_alerts_sent(alert.product_sku, hours=6)
        assert len(results) == 1
        assert results[0].reason == "below_target"

    def test_get_alerts_sent_excludes_old(self) -> None:
        old_ts = "2020-01-01T00:00:00+00:00"
        alert = _make_alert(timestamp=old_ts)
        append_alert(alert)
        results = get_alerts_sent(alert.product_sku, hours=6)
        assert len(results) == 0

    def test_get_alerts_sent_empty_when_no_sku(self) -> None:
        results = get_alerts_sent("NONEXISTENT-SKU", hours=6)
        assert results == []

    def test_multiple_alerts_within_window(self) -> None:
        for reason in ["below_target", "price_drop", "back_in_stock"]:
            alert = _make_alert(reason=reason)
            append_alert(alert)
        results = get_alerts_sent("UX3405CA-PS99T", hours=6)
        assert len(results) == 3

    def test_alert_roundtrip_preserves_fields(self) -> None:
        alert = _make_alert(reason="price_drop")
        alert.previous_price = 1149.00
        append_alert(alert)
        results = get_alerts_sent(alert.product_sku, hours=6)
        assert len(results) == 1
        assert results[0].previous_price == 1149.00


# ---------------------------------------------------------------------------
# update_last_run
# ---------------------------------------------------------------------------


class TestUpdateLastRun:
    def test_creates_last_run_json(self, use_tmp_data_dir: Path) -> None:
        stats = {
            "started_at": "2025-05-27T10:00:00+00:00",
            "completed_at": "2025-05-27T10:01:00+00:00",
            "duration_seconds": 60,
            "products_checked": 3,
            "stores_checked": 5,
            "successful_checks": 14,
            "failed_checks": 1,
            "alerts_sent": 2,
        }
        update_last_run(stats)

        path = use_tmp_data_dir / "last_run.json"
        assert path.exists()
        with path.open() as fh:
            data = json.load(fh)
        assert data["duration_seconds"] == 60
        assert data["alerts_sent"] == 2

    def test_overwrites_previous_run(self, use_tmp_data_dir: Path) -> None:
        update_last_run({"alerts_sent": 1})
        update_last_run({"alerts_sent": 5})

        path = use_tmp_data_dir / "last_run.json"
        with path.open() as fh:
            data = json.load(fh)
        assert data["alerts_sent"] == 5


# ---------------------------------------------------------------------------
# rotate_if_needed
# ---------------------------------------------------------------------------


class TestRotateIfNeeded:
    def test_no_rotation_when_file_missing(self) -> None:
        # Should not raise even if price_log.json doesn't exist
        rotate_if_needed(max_mb=10)

    def test_no_rotation_when_file_small(self, use_tmp_data_dir: Path) -> None:
        # Write a tiny file
        check = _make_check()
        append_check(check)

        price_log_path = use_tmp_data_dir / "price_log.json"
        assert price_log_path.exists()

        rotate_if_needed(max_mb=10)  # threshold = 10 MB, file is tiny

        # File should still exist unchanged
        assert price_log_path.exists()
        # No .gz archive should have been created
        archives = list(use_tmp_data_dir.glob("price_log.*.json.gz"))
        assert len(archives) == 0

    def test_rotation_when_file_exceeds_threshold(
        self, use_tmp_data_dir: Path
    ) -> None:
        # Create a price_log.json that exceeds the threshold
        check = _make_check()
        append_check(check)

        price_log_path = use_tmp_data_dir / "price_log.json"
        assert price_log_path.exists()

        # Rotate with effectively 0 MB threshold
        rotate_if_needed(max_mb=0)

        # Original file should still exist (fresh empty log)
        assert price_log_path.exists()
        fresh_log = load_log()
        assert fresh_log["products"] == {}

        # A gzipped archive should have been created
        archives = list(use_tmp_data_dir.glob("price_log.*.json.gz"))
        assert len(archives) == 1

        # Archive should be readable and contain the old data
        with gzip.open(str(archives[0]), "rb") as fh:
            archived = json.loads(fh.read())
        assert "products" in archived
        assert "UX3405CA-PS99T" in archived["products"]

    def test_rotation_collision_uses_counter(
        self, use_tmp_data_dir: Path
    ) -> None:
        """Two rotations on the same calendar day use a counter suffix."""
        check = _make_check()
        append_check(check)
        rotate_if_needed(max_mb=0)

        # Second rotation — same day
        append_check(_make_check(price=999.00))
        rotate_if_needed(max_mb=0)

        archives = list(use_tmp_data_dir.glob("price_log.*.json.gz"))
        assert len(archives) == 2


# ---------------------------------------------------------------------------
# Lock acquire / release
# ---------------------------------------------------------------------------


class TestLock:
    def test_acquire_and_release(self) -> None:
        acquired = acquire_lock()
        assert acquired is True
        release_lock()

    def test_double_acquire_fails(self) -> None:
        """A second acquire in the same process should fail (already held)."""
        acquired1 = acquire_lock()
        assert acquired1 is True
        try:
            from src import storage as _storage

            if _storage._HAS_FCNTL:
                # Linux/macOS: flock is per open-file-description, so a second
                # open of the same file in the same process can acquire again.
                # Simulate a second process by opening a new fd with NB lock.
                import fcntl as _fcntl  # noqa: PLC0415 — Linux-only, guarded above

                lock_path = str(_storage._lock_path())
                fd2 = os.open(lock_path, os.O_CREAT | os.O_WRONLY)
                try:
                    _fcntl.flock(fd2, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                    # If we got here, the lock wasn't held — unexpected
                    _fcntl.flock(fd2, _fcntl.LOCK_UN)
                    pytest.fail("Expected lock to be held but it was not")
                except (OSError, BlockingIOError):
                    pass  # Correct: lock is held
                finally:
                    os.close(fd2)
            else:
                # Windows fallback: file-existence guard.
                # Lock file must exist while the lock is held.
                assert _storage._lock_path().exists(), (
                    "Lock file should exist while lock is held"
                )
                # A second acquire_lock() call should return False because
                # the file already exists (O_EXCL semantics).
                acquired2 = acquire_lock()
                assert acquired2 is False, (
                    "Second acquire should fail while lock is held"
                )
        finally:
            release_lock()

    def test_release_removes_lock_file(self, use_tmp_data_dir: Path) -> None:
        acquire_lock()
        release_lock()
        lock_path = use_tmp_data_dir / ".lock"
        assert not lock_path.exists()

    def test_stale_lock_is_removed(self, use_tmp_data_dir: Path) -> None:
        """A lock file older than 1 hour is treated as an orphan and removed."""
        lock_path = use_tmp_data_dir / ".lock"
        lock_path.write_text("99999")  # fake stale lock with a dead PID
        # Backdate the file's mtime by 2 hours
        old_time = time.time() - 7200
        os.utime(str(lock_path), (old_time, old_time))

        acquired = acquire_lock()
        assert acquired is True
        release_lock()
