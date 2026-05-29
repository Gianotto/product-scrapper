# n8n Webhook Setup

This document explains how to configure the n8n workflow that receives price alerts from the monitor and forwards them to Telegram.

---

## Prerequisites

- n8n running and accessible (e.g., `https://your-n8n-host`)
- A Telegram bot token (create one via [@BotFather](https://t.me/BotFather))
- Your Telegram chat ID (see below)

---

## Step 1: Find Your Telegram Chat ID

1. Start a conversation with [@userinfobot](https://t.me/userinfobot) on Telegram
2. It will reply with your numeric user ID — this is your `chat_id`

---

## Step 2: Create the n8n Workflow

### 2a. Webhook Trigger Node

1. Add a **Webhook** node
2. Set **HTTP Method** to `POST`
3. Set **Path** to `notebook-price-alert`
4. Set **Authentication** to `Header Auth` (recommended):
   - Header name: `X-API-Key`
   - Header value: a secret string you choose
5. Click **Listen for Test Event** to get the webhook URL
6. Note the URL — it will be: `https://your-n8n-host/webhook/notebook-price-alert`

### 2b. Telegram Node

1. Add a **Telegram** node connected to the Webhook node
2. Set **Operation** to `Send Message`
3. Configure **Credentials**: add your bot token
4. Set **Chat ID** to your numeric user ID from Step 1
5. Set **Text** to:
   ```
   {{ $json.message }}
   ```
6. Enable **Parse Mode**: `Markdown` (optional — the message field is plain text)

### 2c. Optional: If/Filter Node

Add an **If** node between the Webhook and Telegram nodes to filter alerts:
- Condition: `{{ $json.event_type }}` equals `price_alert`
- This prevents forwarding unexpected payloads

---

## Step 3: Activate the Workflow

1. Click **Activate** to enable the workflow
2. The webhook URL is now live

---

## Step 4: Configure the Monitor

Set the webhook URL in your `.env` file:

```bash
N8N_WEBHOOK_URL=https://your-n8n-host/webhook/notebook-price-alert
```

If you enabled `X-API-Key` authentication, the monitor does not currently send this header — you would need to either disable header auth in n8n or add the header to `src/alerts.py`'s `_build_payload()`.

---

## Step 5: Test the Integration

Send a test payload directly to the webhook:

```bash
curl -X POST https://your-n8n-host/webhook/notebook-price-alert \
  -H "Content-Type: application/json" \
  -d '{"event_type": "price_alert", "message": "🔥 Test alert — setup is working!"}'
```

You should receive the message on Telegram within a few seconds.

You can also test end-to-end with the monitor in dry-run mode:

```bash
# Dry-run won't actually POST to the webhook, but verifies the config loads
python monitor.py --dry-run --verbose
```

---

## Payload Reference

The monitor sends this JSON structure on each alert:

```json
{
  "event_type": "price_alert",
  "timestamp": "2026-06-15T14:30:00Z",
  "product": {
    "sku": "UX3405CA-PS99T",
    "name": "ASUS Zenbook 14 OLED PS99T..."
  },
  "alert": {
    "reason": "below_target",
    "current_price": 1049.00,
    "target_price": 1099.00,
    "previous_price": 1299.00,
    "discount_from_target_percent": 4.5,
    "currency": "USD"
  },
  "store": {
    "name": "bestbuy",
    "url": "https://www.bestbuy.com/site/...",
    "in_stock": true
  },
  "message": "🔥 PRECO ABAIXO DO TARGET!\n\nASUS Zenbook 14 OLED PS99T...\nBest Buy: $1,049.00 (target $1,099.00)\nEm estoque: ✅\n\nhttps://www.bestbuy.com/site/..."
}
```

**Alert reasons:**
- `below_target` — price at or below your configured `target_price`
- `price_drop` — price dropped ≥ 5% since last check
- `back_in_stock` — item was out of stock and is now available

---

## Troubleshooting

**Webhook not receiving requests:**
- Check that the workflow is **Activated** in n8n (not just saved)
- Verify `N8N_WEBHOOK_URL` in `.env` matches the exact URL shown in the Webhook node
- Check n8n logs for incoming requests

**Telegram message not arriving:**
- Test the Telegram node manually inside n8n
- Verify the bot has started a conversation with you (send `/start` to your bot)
- Confirm the `chat_id` is correct (it should be a number, e.g., `123456789`)

**Alert sent but not received after cooldown:**
- The monitor enforces a 6-hour cooldown per alert type per product
- Check `data/price_log.json` → `alerts_sent` to see recent alerts
