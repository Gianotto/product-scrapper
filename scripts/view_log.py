#!/usr/bin/env python3
"""View price history from data/price_log.json.

Usage:
    python scripts/view_log.py                        # Latest check per product+store
    python scripts/view_log.py --sku UX3405CA-PS99T   # Filter to one SKU
    python scripts/view_log.py --last 10              # Show last N checks total
    python scripts/view_log.py --alerts               # Show alerts sent
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "./data"))


def _load_log() -> dict:
    path = _data_dir() / "price_log.json"
    if not path.exists():
        print(f"No price log found at {path}", file=sys.stderr)
        sys.exit(0)
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_price(price) -> str:
    if price is None:
        return "N/A"
    try:
        return f"${float(price):,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_stock(in_stock) -> str:
    if in_stock is None:
        return "N/A"
    return "Yes" if in_stock else "No"


def _fmt_ts(ts_str: str) -> str:
    """Format ISO 8601 timestamp to 'YYYY-MM-DD HH:MM' local or UTC."""
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(ts_str)[:16] if ts_str else "N/A"


def _print_table(rows: list[dict], columns: list[tuple[str, str, int]]) -> None:
    """Print a simple text table.

    columns: list of (header, key, width)
    """
    # Header
    header = "  ".join(h.ljust(w) for h, _, w in columns)
    sep = "  ".join("-" * w for _, _, w in columns)
    print(header)
    print(sep)
    for row in rows:
        line = "  ".join(str(row.get(k, "")).ljust(w)[:w] for _, k, w in columns)
        print(line)
    print(f"\n{len(rows)} record(s)")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def _all_checks(log: dict, sku_filter: str | None) -> list[dict]:
    """Return all check records, optionally filtered by SKU."""
    checks = []
    for sku, prod_data in log.get("products", {}).items():
        if sku_filter and sku != sku_filter:
            continue
        for c in prod_data.get("checks", []):
            checks.append({
                "sku": sku,
                "store": c.get("store", ""),
                "price": c.get("price"),
                "in_stock": c.get("in_stock"),
                "timestamp": c.get("timestamp", ""),
                "error": c.get("error"),
                "success": c.get("success", False),
            })
    # Sort by timestamp descending
    checks.sort(key=lambda x: x["timestamp"], reverse=True)
    return checks


def _latest_per_product_store(checks: list[dict]) -> list[dict]:
    """Keep only the most recent check per (sku, store) pair."""
    seen: dict[tuple, dict] = {}
    for c in checks:
        key = (c["sku"], c["store"])
        if key not in seen:
            seen[key] = c
    result = list(seen.values())
    result.sort(key=lambda x: (x["sku"], x["store"]))
    return result


def _build_check_display_rows(checks: list[dict]) -> list[dict]:
    rows = []
    for c in checks:
        if c.get("error"):
            price_display = "N/A"
            note = f"(failed: {c['error'][:30]})"
        else:
            price_display = _fmt_price(c["price"])
            note = ""
        rows.append({
            "sku": c["sku"],
            "store": c["store"],
            "price": price_display,
            "in_stock": _fmt_stock(c.get("in_stock")),
            "timestamp": _fmt_ts(c["timestamp"]) + ("  " + note if note else ""),
        })
    return rows


def view_latest(log: dict, sku_filter: str | None) -> None:
    """Show the latest check per product+store."""
    all_c = _all_checks(log, sku_filter)
    latest = _latest_per_product_store(all_c)
    rows = _build_check_display_rows(latest)

    if not rows:
        print("No checks found.")
        return

    columns = [
        ("SKU", "sku", 22),
        ("Store", "store", 12),
        ("Price", "price", 12),
        ("In Stock", "in_stock", 10),
        ("Timestamp", "timestamp", 40),
    ]
    _print_table(rows, columns)


def view_last_n(log: dict, n: int, sku_filter: str | None) -> None:
    """Show the last N checks."""
    all_c = _all_checks(log, sku_filter)
    subset = all_c[:n]
    rows = _build_check_display_rows(subset)

    if not rows:
        print("No checks found.")
        return

    columns = [
        ("SKU", "sku", 22),
        ("Store", "store", 12),
        ("Price", "price", 12),
        ("In Stock", "in_stock", 10),
        ("Timestamp", "timestamp", 40),
    ]
    _print_table(rows, columns)


def view_alerts(log: dict, sku_filter: str | None) -> None:
    """Show all alerts sent."""
    alerts = []
    for sku, prod_data in log.get("products", {}).items():
        if sku_filter and sku != sku_filter:
            continue
        for a in prod_data.get("alerts_sent", []):
            alerts.append({
                "sku": sku,
                "store": a.get("store", ""),
                "reason": a.get("reason", ""),
                "price": a.get("price"),
                "target": a.get("target_price"),
                "timestamp": a.get("timestamp", ""),
            })

    alerts.sort(key=lambda x: x["timestamp"], reverse=True)

    if not alerts:
        print("No alerts found.")
        return

    rows = [
        {
            "sku": a["sku"],
            "store": a["store"],
            "reason": a["reason"],
            "price": _fmt_price(a["price"]),
            "target": _fmt_price(a["target"]),
            "timestamp": _fmt_ts(a["timestamp"]),
        }
        for a in alerts
    ]

    columns = [
        ("SKU", "sku", 22),
        ("Store", "store", 12),
        ("Reason", "reason", 15),
        ("Price", "price", 12),
        ("Target", "target", 12),
        ("Timestamp", "timestamp", 20),
    ]
    _print_table(rows, columns)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View price history from data/price_log.json",
    )
    parser.add_argument(
        "--sku",
        metavar="SKU",
        default=None,
        help="Filter output to a specific product SKU.",
    )
    parser.add_argument(
        "--last",
        metavar="N",
        type=int,
        default=None,
        help="Show last N checks instead of latest per product+store.",
    )
    parser.add_argument(
        "--alerts",
        action="store_true",
        help="Show alerts sent instead of price checks.",
    )
    args = parser.parse_args()

    log = _load_log()

    updated = log.get("last_updated", "unknown")
    print(f"Price log — last updated: {_fmt_ts(updated)}\n")

    if args.alerts:
        view_alerts(log, sku_filter=args.sku)
    elif args.last is not None:
        view_last_n(log, n=args.last, sku_filter=args.sku)
    else:
        view_latest(log, sku_filter=args.sku)


if __name__ == "__main__":
    main()
