# Notebook Price Monitor

A Python CLI tool that monitors ASUS Zenbook laptop prices across five US stores (Best Buy, Amazon, Newegg, ASUS Shop, eBay) and sends Telegram alerts via an n8n webhook when prices drop below your targets. Designed to run on a Linux server as a cron job alongside n8n.

---

## Quick Start

### 1. Install

```bash
git clone <repo-url> price-monitor
cd price-monitor
bash scripts/install.sh
```

This creates a `.venv`, installs dependencies, and copies the config templates.

### 2. Configure

```bash
# Set your n8n webhook URL (required) and optional API keys
nano .env

# Set target prices and which products/stores to monitor
nano config.yaml
```

Minimum `.env` change needed:

```
N8N_WEBHOOK_URL=https://your-n8n-server/webhook/notebook-price-alert
```

### 3. Test (dry run — no writes, no real alerts)

```bash
.venv/bin/python monitor.py --dry-run --verbose
```

You should see a summary table printed to stdout.

### 4. Run for real

```bash
.venv/bin/python monitor.py
```

---

## Configuration Reference (`config.yaml`)

| Field | Description |
|---|---|
| `general.request_timeout_seconds` | HTTP timeout per request (default: 30) |
| `general.max_retries` | Retry attempts on network failure (default: 3) |
| `general.user_agents_rotation` | Rotate browser user-agents to reduce blocking |
| `stores.<name>.enabled` | Set to `false` to skip a store entirely |
| `stores.<name>.rate_limit_seconds` | Pause between requests to the same store |
| `stores.amazon.use_scraperapi` | Route Amazon requests via ScraperAPI (requires `SCRAPERAPI_KEY` in `.env`) |
| `products[].sku` | Product identifier — used as the unique key in logs |
| `products[].name` | Human-readable product name (appears in alerts) |
| `products[].target_price` | Alert is sent when price is at or below this value |
| `products[].must_have_terms` | Result title must contain ALL of these terms |
| `products[].blocklist_terms` | Result title must not contain ANY of these terms |
| `products[].stores` | Map of `store_name: search_url` for this product |
| `alerts.webhook_url` | n8n webhook URL — read from `${N8N_WEBHOOK_URL}` in `.env` |
| `alerts.triggers.price_drop_percent` | Alert if price drops this percentage since last check |
| `alerts.triggers.below_target` | Alert whenever price is at or below `target_price` |
| `alerts.triggers.back_in_stock` | Alert when item was out-of-stock and is now available |
| `alerts.cooldown_minutes` | Minimum gap between identical alerts (default: 360 = 6 h) |

---

## CLI Flags (`monitor.py`)

```
python monitor.py [OPTIONS]

Options:
  --config PATH     Path to config.yaml (default: ./config.yaml)
  --dry-run         Run without saving data or sending real alerts; prints summary table
  --verbose         Set log level to DEBUG (shows HTTP requests, selector matches, etc.)
  --store NAME      Only check one store (e.g. --store bestbuy)
  --product SKU     Only check one product SKU (e.g. --product UX3405CA-PS99T)
```

Exit codes: `0` = all checks succeeded, `1` = partial failure, `2` = fatal error.

---

## View Price History

```bash
# Latest check per product+store
python scripts/view_log.py

# Filter to one product
python scripts/view_log.py --sku UX3405CA-PS99T

# Show last 20 checks
python scripts/view_log.py --last 20

# Show alerts sent
python scripts/view_log.py --alerts
```

Example output:

```
SKU                     Store         Price         In Stock    Timestamp
----------------------  ------------  ------------  ----------  ----------------------------------------
UX3405CA-PS99T          bestbuy       $1,299.00     Yes         2026-05-28 06:00
UX3405CA-PS99T          amazon        N/A           N/A         2026-05-28 06:00  (failed: Timeout)
```

---

## Cron Setup

```bash
bash scripts/install_cron.sh
```

This prompts for confirmation, then adds a crontab entry that runs the monitor at **06:00 and 18:00 daily**. Logs are appended to `logs/cron.log`.

To verify the installed cron: `crontab -l`

---

## Troubleshooting

### Amazon blocks requests

Amazon is the most likely to block scraping. Options:

1. Set `stores.amazon.use_scraperapi: true` in `config.yaml` and add `SCRAPERAPI_KEY` to `.env`.
2. Temporarily disable: `stores.amazon.enabled: false`.
3. Increase the rate limit: `stores.amazon.rate_limit_seconds: 10`.

Run with `--verbose` to see what HTML is returned.

### Alerts don't arrive in Telegram

1. Check that `N8N_WEBHOOK_URL` is set correctly in `.env`.
2. Test the webhook directly:
   ```bash
   curl -X POST "$N8N_WEBHOOK_URL" \
     -H "Content-Type: application/json" \
     -d '{"message": "test alert"}'
   ```
3. Check n8n execution logs for errors.
4. Verify your Telegram bot token and chat ID in n8n.
5. See `docs/N8N_SETUP.md` for full n8n setup instructions.

### Log grows too large

The price log auto-rotates when it exceeds 10 MB: the current file is compressed
to `data/price_log.YYYY-MM-DD.json.gz` and a fresh file is started. Old `.gz`
files can be deleted manually once you no longer need that history.

### Another instance is already running

```
Could not acquire lock — another instance may be running.
```

If you're sure no other instance is running, delete the stale lock file:

```bash
rm data/.lock
```

---

## Tech Stack

| Component | Library / Version |
|---|---|
| Runtime | Python 3.11+ |
| Logging | [loguru](https://github.com/Delgan/loguru) |
| HTML parsing | [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) + lxml |
| HTTP retry | [tenacity](https://github.com/jd/tenacity) |
| User-agent rotation | [fake-useragent](https://github.com/fake-useragent/fake-useragent) |
| HTTP | [requests](https://docs.python-requests.org/) |
| Config parsing | [PyYAML](https://pyyaml.org/) + [python-dotenv](https://github.com/theskumar/python-dotenv) |
| Alerts | n8n webhook → Telegram |
