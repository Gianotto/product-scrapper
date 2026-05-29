# Architecture

Technical design decisions for the notebook price monitor.

---

## Directory Structure

```
price-monitor/
├── monitor.py              # CLI entrypoint — argument parsing, logging setup, exit codes
├── config.example.yaml     # Configuration template (copy to config.yaml)
├── .env.example            # Environment variable template (copy to .env)
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # Dev/test dependencies
│
├── src/
│   ├── config.py           # Config loader — parses config.yaml + .env, returns AppConfig
│   ├── models.py           # Dataclasses: Product, PriceCheck, AlertEvent
│   ├── orchestrator.py     # Main loop: iterates products × stores, calls scrapers + alerts
│   ├── storage.py          # JSON persistence layer (price_log.json, last_run.json, lock)
│   ├── alerts.py           # n8n webhook sender + message formatter
│   └── scrapers/
│       ├── __init__.py     # Factory function: get_scraper(store_name, config)
│       ├── base.py         # BaseScraper ABC + pick_best_result() + filter_results()
│       ├── bestbuy.py
│       ├── amazon.py
│       ├── newegg.py
│       ├── asus_shop.py
│       └── ebay.py
│
├── scripts/
│   ├── install.sh          # First-time setup: venv, deps, config copy
│   ├── install_cron.sh     # Configure crontab (6:00 and 18:00 daily)
│   └── view_log.py         # CLI to display price_log.json as a readable table
│
├── data/                   # Runtime data (gitignored)
│   ├── price_log.json      # Full price history + alerts
│   ├── last_run.json       # Summary of most recent execution
│   └── .lock               # Process lock file (deleted after each run)
│
├── logs/                   # Log files (gitignored)
│   ├── monitor.log         # Rotating loguru log (10 MB / 30 days)
│   └── cron.log            # stdout/stderr captured by crontab
│
├── tests/                  # pytest test suite
└── docs/                   # This directory
```

---

## Design Decisions

### JSON file storage instead of SQLite or Postgres

The monitor runs infrequently (twice daily) and stores a modest amount of data
(a few KB per run). A relational database would require a running server process,
schema migrations, and additional dependencies. A JSON file:

- Requires zero infrastructure — no database server to configure or maintain.
- Is human-readable and inspectable with any text editor or `scripts/view_log.py`.
- Can be backed up with a simple `cp`.
- Corrupt entries can be recovered by editing the file directly.
- Performs adequately at this data volume (<10 MB before rotation triggers).

The file is written atomically (write to `.tmp` → `rename`) to prevent partial
writes from corrupting the log on crash or disk-full.

### Sequential scraping instead of parallel

Stores are checked one at a time, with configurable rate-limit pauses between
requests:

1. **Less detectable** — parallel requests from the same IP trigger anti-bot
   systems faster than sequential requests spaced several seconds apart.
2. **Simpler code** — no thread pool, no shared state, no race conditions.
3. **Sufficient throughput** — checking 3 products × 5 stores = 15 requests, each
   with a 3–5 s pause, completes in under 90 seconds. Acceptable for twice-daily
   runs.

`config.yaml` exposes a `parallel_requests` flag for future use, but it is `false`
by default and not yet implemented.

### Scraper resilience strategy

Each scraper is designed to fail gracefully:

- **Multiple CSS selectors** — each scraper tries a list of selectors in priority
  order. If a site updates its HTML, an older selector will likely still match
  until the scraper is updated.
- **User-agent rotation** — `fake-useragent` provides realistic browser UA strings,
  reducing the likelihood of being served a bot-detection page.
- **Retry with backoff** — `tenacity` retries transient network errors (up to 3
  attempts, 5 s apart) before recording a failure.
- **Graceful failure** — if a scraper raises any exception, the orchestrator logs
  the error, records a `PriceCheck(success=False, error=...)` entry, increments
  `failed_checks`, and continues with the next store. A single broken scraper does
  not abort the run.
- **Title filtering** — `filter_results()` in `BaseScraper` applies `must_have_terms`
  and `blocklist_terms` to prevent alerting on wrong variants (e.g. a 60 Hz panel
  or a refurbished unit).

### Alert cooldown system

Alert evaluation lives in `orchestrator.check_and_alert()`. Before sending an
alert, the system checks `storage.get_alerts_sent(sku, hours=cooldown_hours)`.
If an alert with the same `(reason, store)` was sent within the cooldown window
(default: 6 hours), it is suppressed. This prevents a flood of repeated
notifications if the price stays below target across multiple runs.

The cooldown window is configurable per deployment (`alerts.cooldown_minutes` in
`config.yaml`).

### Lock file mechanism

`data/.lock` prevents two cron executions from running simultaneously (e.g. if a
previous run is still in progress when the next one fires).

On **Linux/macOS**, `fcntl.flock` provides a kernel-enforced advisory exclusive
lock on the file descriptor. On **Windows** (dev/CI only), a file-existence guard
(`O_EXCL`) is used as a best-effort fallback.

Orphan locks older than 1 hour are automatically removed at startup to recover
from crashes. The lock is always released in a `finally` block.

---

## Data Flow

```
crontab / CLI
     │
     ▼
monitor.py          ← argparse + logging setup
     │
     ▼
orchestrator.run_all_checks()
     │
     ├─ for each product × store:
     │       │
     │       ├─ get_scraper(store_name)     → BaseScraper subclass
     │       ├─ scraper.search(product, url) → list[PriceCheck]
     │       ├─ pick_best_result()           → PriceCheck | None
     │       ├─ storage.append_check()       → price_log.json
     │       └─ check_and_alert()
     │               │
     │               ├─ storage.get_last_check()    ← compare with previous price
     │               ├─ storage.get_alerts_sent()   ← cooldown check
     │               ├─ alerts.send_alert()          → n8n webhook → Telegram
     │               └─ storage.append_alert()       → price_log.json
     │
     └─ storage.update_last_run()           → last_run.json
```
