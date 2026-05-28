"""
JSON-based persistence layer for the price monitor application.

Two files are used:
- price_log.json  — full history of checks and alerts, one record per product.
- last_run.json   — lightweight summary of the most recent cron execution.

All writes are atomic: data is flushed to a .tmp file then renamed into place.
A lock file at ``data/.lock`` prevents concurrent executions.

Log rotation: when price_log.json exceeds ``max_mb`` MB it is compressed to
``price_log.YYYY-MM-DD.json.gz`` and a fresh file is started.

Platform note
-------------
``fcntl`` (POSIX advisory file locking) is Linux/macOS only and is used in
production.  On Windows (CI / local dev) we fall back to a best-effort
file-existence lock so the code remains importable and testable.
The ``_HAS_FCNTL`` flag controls which path is taken at runtime; type checkers
and linters on Windows will see the else-branch, which is intentional.
"""

from __future__ import annotations

import gzip
import importlib as _importlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from src.models import AlertEvent, PriceCheck

# ---------------------------------------------------------------------------
# Platform-conditional locking primitives
# ---------------------------------------------------------------------------
# fcntl is POSIX-only (Linux/macOS).  We import it via importlib so that
# static analysers on Windows don't flag the import as unreachable — they
# can't resolve importlib.import_module at analysis time.
# Production always runs on Linux, so _fcntl_mod is always the real module
# there.  On Windows (dev/CI) we fall back to a file-existence guard.

try:
    _fcntl_mod = _importlib.import_module("fcntl")
    _HAS_FCNTL: bool = True
except ModuleNotFoundError:
    _fcntl_mod = None  # type: ignore[assignment]
    _HAS_FCNTL = False


# ---------------------------------------------------------------------------
# Paths — resolved relative to the DATA_DIR env var, defaulting to ./data
# ---------------------------------------------------------------------------


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "./data"))


def _price_log_path() -> Path:
    return _data_dir() / "price_log.json"


def _last_run_path() -> Path:
    return _data_dir() / "last_run.json"


def _lock_path() -> Path:
    return _data_dir() / ".lock"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write *data* as JSON to *path* atomically via a temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    # Atomic rename (same filesystem)
    tmp_path.replace(path)


def _empty_log() -> dict[str, Any]:
    return {
        "version": "1.0",
        "created_at": _now_utc(),
        "last_updated": _now_utc(),
        "products": {},
    }


# ---------------------------------------------------------------------------
# Lock management
# ---------------------------------------------------------------------------

_LOCK_MAX_AGE_SECONDS = 3600  # 1 hour — treat older locks as orphans

# Module-level handle so that acquire_lock / release_lock share the same fd.
_lock_fd: int | None = None


def _remove_stale_lock() -> None:
    """Remove the lock file if it is older than _LOCK_MAX_AGE_SECONDS."""
    lock_path = _lock_path()
    if lock_path.exists():
        age = time.time() - lock_path.stat().st_mtime
        if age > _LOCK_MAX_AGE_SECONDS:
            lock_path.unlink(missing_ok=True)


def acquire_lock() -> bool:
    """
    Acquire an exclusive advisory lock using ``data/.lock``.

    On Linux/macOS uses ``fcntl.flock`` (non-blocking).
    On Windows uses a best-effort file-existence guard (adequate for tests).

    Returns True if the lock was acquired, False if another process holds it.
    Orphan locks older than 1 hour are removed automatically.
    """
    global _lock_fd  # noqa: PLW0603

    lock_path = _lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    _remove_stale_lock()

    if _HAS_FCNTL:
        # POSIX path — production behaviour
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY)
            _fcntl_mod.flock(fd, _fcntl_mod.LOCK_EX | _fcntl_mod.LOCK_NB)
            os.write(fd, str(os.getpid()).encode())
            _lock_fd = fd
            return True
        except (OSError, BlockingIOError):
            return False
    else:
        # Windows fallback — file-existence guard
        if lock_path.exists():
            return False
        try:
            # O_EXCL makes this atomic on NTFS
            fd = os.open(
                str(lock_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            os.write(fd, str(os.getpid()).encode())
            _lock_fd = fd
            return True
        except FileExistsError:
            return False


def release_lock() -> None:
    """Release the lock acquired by :func:`acquire_lock`."""
    global _lock_fd  # noqa: PLW0603

    if _lock_fd is not None:
        try:
            if _HAS_FCNTL:
                _fcntl_mod.flock(_lock_fd, _fcntl_mod.LOCK_UN)
            os.close(_lock_fd)
        except OSError:
            pass
        _lock_fd = None

    _lock_path().unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Core log I/O
# ---------------------------------------------------------------------------


def load_log() -> dict[str, Any]:
    """
    Load price_log.json and return its parsed content.

    Creates and returns a fresh empty log structure if the file does not exist.
    If the file is corrupt (invalid JSON), it is backed up with a timestamped
    suffix and a fresh empty log is returned.
    """
    path = _price_log_path()
    if not path.exists():
        return _empty_log()
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        corrupt_path = path.with_suffix(
            f".corrupt.{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        )
        logger.error(
            "Corrupt price_log.json: {e}. Backing up to {backup} and starting fresh.",
            e=e,
            backup=corrupt_path,
        )
        path.rename(corrupt_path)
        return _empty_log()


def save_log(data: dict[str, Any]) -> None:
    """Persist *data* as the price_log.json (atomic write)."""
    data["last_updated"] = _now_utc()
    _atomic_write(_price_log_path(), data)


# ---------------------------------------------------------------------------
# Check operations
# ---------------------------------------------------------------------------


def append_check(check: PriceCheck) -> None:
    """Append a PriceCheck result to the product's checks list in price_log.json."""
    log = load_log()
    products = log.setdefault("products", {})
    sku = check.product_sku

    if sku not in products:
        products[sku] = {"checks": [], "alerts_sent": []}

    products[sku].setdefault("checks", []).append(check.to_dict())
    save_log(log)


def get_last_check(sku: str, store: str) -> PriceCheck | None:
    """
    Return the most recent PriceCheck for *sku* on *store*, or None if none exists.
    """
    log = load_log()
    checks_raw: list[dict[str, Any]] = (
        log.get("products", {}).get(sku, {}).get("checks", [])
    )
    # Iterate in reverse to find the latest matching entry
    for raw in reversed(checks_raw):
        if raw.get("store") == store:
            return PriceCheck.from_dict(raw)
    return None


# ---------------------------------------------------------------------------
# Alert operations
# ---------------------------------------------------------------------------


def get_alerts_sent(sku: str, hours: int | float = 6) -> list[AlertEvent]:
    """
    Return AlertEvents for *sku* sent within the last *hours* hours.
    """
    log = load_log()
    alerts_raw: list[dict[str, Any]] = (
        log.get("products", {}).get(sku, {}).get("alerts_sent", [])
    )
    cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
    result: list[AlertEvent] = []
    for raw in alerts_raw:
        try:
            ts = datetime.fromisoformat(raw["timestamp"]).timestamp()
        except (KeyError, ValueError):
            continue
        if ts >= cutoff:
            result.append(AlertEvent.from_dict(raw))
    return result


def append_alert(alert: AlertEvent) -> None:
    """Append an AlertEvent to the product's alerts_sent list in price_log.json."""
    log = load_log()
    products = log.setdefault("products", {})
    sku = alert.product_sku

    if sku not in products:
        products[sku] = {"checks": [], "alerts_sent": []}

    products[sku].setdefault("alerts_sent", []).append(alert.to_dict())
    save_log(log)


# ---------------------------------------------------------------------------
# last_run.json
# ---------------------------------------------------------------------------


def update_last_run(stats: dict[str, Any]) -> None:
    """
    Overwrite last_run.json with *stats*.

    Expected keys (all optional): started_at, completed_at, duration_seconds,
    products_checked, stores_checked, successful_checks, failed_checks, alerts_sent.
    """
    _atomic_write(_last_run_path(), stats)


# ---------------------------------------------------------------------------
# Log rotation
# ---------------------------------------------------------------------------


def rotate_if_needed(max_mb: int = 10) -> None:
    """
    If price_log.json exceeds *max_mb* MB, compress it to a dated archive and
    start a fresh price_log.json.
    """
    path = _price_log_path()
    if not path.exists():
        return

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb < max_mb:
        return

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_path = _data_dir() / f"price_log.{date_str}.json.gz"

    # If an archive for today already exists, append a counter to avoid collision
    counter = 0
    while archive_path.exists():
        counter += 1
        archive_path = _data_dir() / f"price_log.{date_str}.{counter}.json.gz"

    with path.open("rb") as f_in:
        with gzip.open(str(archive_path), "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    # Write a fresh log (preserve version/created_at convention)
    _atomic_write(path, _empty_log())
