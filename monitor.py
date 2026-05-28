#!/usr/bin/env python3
"""Notebook Price Monitor — main entrypoint.

Usage:
    python monitor.py [--config PATH] [--dry-run] [--verbose]
                      [--store NAME] [--product SKU]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _configure_logging(verbose: bool, log_file: Path) -> None:
    """Set up loguru sinks: stderr + rotating file."""
    from loguru import logger

    logger.remove()  # Remove default sink

    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level, colorize=True)
    logger.add(
        str(log_file),
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8",
    )


def _print_summary(stats) -> None:
    """Print a plain-text dry-run summary table to stdout."""
    width = 42
    sep = "-" * width
    print(sep)
    print(f"  {'PRICE MONITOR — DRY RUN SUMMARY':^{width - 4}}")
    print(sep)
    print(f"  {'Started at':<22} {stats.started_at}")
    print(f"  {'Completed at':<22} {stats.completed_at}")
    print(f"  {'Duration (s)':<22} {stats.duration_seconds:.2f}")
    print(sep)
    print(f"  {'Products checked':<22} {stats.products_checked}")
    print(f"  {'Stores checked':<22} {stats.stores_checked}")
    print(f"  {'Successful checks':<22} {stats.successful_checks}")
    print(f"  {'Failed checks':<22} {stats.failed_checks}")
    print(f"  {'Alerts (dry-run)':<22} {stats.alerts_sent}")
    print(sep)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="monitor",
        description="Notebook Price Monitor — check prices and send alerts.",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default="config.yaml",
        help="Path to config.yaml (default: ./config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without saving data or sending real alerts.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Set log level to DEBUG.",
    )
    parser.add_argument(
        "--store",
        metavar="NAME",
        default=None,
        help="Only check this store (e.g. bestbuy).",
    )
    parser.add_argument(
        "--product",
        metavar="SKU",
        default=None,
        help="Only check this product SKU.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point.  Returns exit code (0 = success, 1 = partial failure, 2 = fatal)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Ensure logs directory exists before configuring file sink
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "monitor.log"

    _configure_logging(verbose=args.verbose, log_file=log_file)

    from loguru import logger

    # --- Load config ---
    config_path = Path(args.config)
    if not config_path.exists():
        example = Path("config.example.yaml")
        msg = (
            f"ERROR: Configuration file not found: {config_path}\n"
            f"Copy config.example.yaml to config.yaml and customise it."
        )
        if example.exists():
            msg += f"\n  cp {example} config.yaml"
        print(msg, file=sys.stderr)
        return 2

    try:
        from src.config import load_config

        config = load_config(args.config)
    except Exception as exc:
        logger.error("Failed to load config from {path}: {exc}", path=args.config, exc=exc)
        return 2

    logger.info(
        "Starting price monitor | config={config} dry_run={dry_run} "
        "store_filter={store} product_filter={product}",
        config=args.config,
        dry_run=args.dry_run,
        store=args.store,
        product=args.product,
    )

    # --- Run checks ---
    try:
        from src.orchestrator import run_all_checks

        stats = run_all_checks(
            config=config,
            dry_run=args.dry_run,
            store_filter=args.store,
            product_filter=args.product,
        )
    except Exception as exc:
        logger.exception("Fatal error during price checks: {exc}", exc=exc)
        return 2

    # --- Report ---
    if args.dry_run:
        _print_summary(stats)

    logger.info(
        "Run complete: {ok} ok / {fail} failed / {alerts} alerts in {dur:.1f}s",
        ok=stats.successful_checks,
        fail=stats.failed_checks,
        alerts=stats.alerts_sent,
        dur=stats.duration_seconds,
    )

    if stats.failed_checks > 0 and stats.successful_checks == 0:
        return 1  # All checks failed
    if stats.failed_checks > 0:
        return 1  # Partial failure
    return 0


if __name__ == "__main__":
    sys.exit(main())
