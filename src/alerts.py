"""
Alert delivery module for the price monitor application.

Sends formatted price-alert notifications to the configured n8n webhook.
The payload includes a human-readable message field in Brazilian Portuguese.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import requests
from loguru import logger

from src.models import AlertEvent

# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _discount_percent(current: float, reference: float) -> float:
    """Return how many percent *current* is below *reference* (positive = discount)."""
    if reference <= 0:
        return 0.0
    return round((reference - current) / reference * 100, 2)


def _build_message(event: AlertEvent) -> str:
    """Build a human-readable alert message in Brazilian Portuguese."""
    reason_map = {
        "below_target": "PRECO ABAIXO DO TARGET",
        "price_drop": "QUEDA DE PRECO DETECTADA",
        "back_in_stock": "PRODUTO DE VOLTA AO ESTOQUE",
    }
    header = reason_map.get(event.reason, "ALERTA DE PRECO")

    lines = [
        f"{header}!",
        "",
        f"Produto : {event.product_name}",
        f"Loja    : {event.store.replace('_', ' ').title()}",
        f"Preco   : US$ {event.price:.2f}",
        f"Target  : US$ {event.target_price:.2f}",
    ]

    if event.reason == "below_target":
        discount = _discount_percent(event.price, event.target_price)
        lines.append(f"Desconto: {discount:.1f}% abaixo do target")

    if event.reason == "price_drop" and event.previous_price is not None:
        drop = _discount_percent(event.price, event.previous_price)
        lines.append(
            f"Queda   : de US$ {event.previous_price:.2f} "
            f"para US$ {event.price:.2f} ({drop:.1f}%)"
        )

    lines += [
        "",
        f"Link    : {event.url}",
        f"Horario : {event.timestamp}",
    ]

    return "\n".join(lines)


def _build_payload(event: AlertEvent) -> dict[str, Any]:
    """Construct the full JSON payload for the n8n webhook."""
    discount_from_target = _discount_percent(event.price, event.target_price)

    return {
        "event_type": "price_alert",
        "timestamp": event.timestamp,
        "product": {
            "sku": event.product_sku,
            "name": event.product_name,
        },
        "alert": {
            "reason": event.reason,
            "current_price": event.price,
            "target_price": event.target_price,
            "previous_price": event.previous_price,
            "discount_from_target_percent": discount_from_target,
            "currency": "USD",
        },
        "store": {
            "name": event.store,
            "url": event.url,
            "in_stock": True,
        },
        "message": _build_message(event),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def send_alert(
    event: AlertEvent,
    webhook_url: str,
    dry_run: bool = False,
) -> bool:
    """
    Send a price-alert notification to the n8n webhook.

    Parameters
    ----------
    event:
        The alert event to send.
    webhook_url:
        Full URL of the n8n webhook endpoint.
    dry_run:
        When True, log what would be sent without making any HTTP request.

    Returns
    -------
    bool
        True if the webhook responded with a 2xx status code (or in dry_run mode).
        False on HTTP error, timeout, or non-2xx response.
    """
    payload = _build_payload(event)

    if dry_run:
        logger.info(
            "[DRY RUN] Would POST alert to {url}\nPayload:\n{payload}",
            url=webhook_url,
            payload=json.dumps(payload, indent=2, ensure_ascii=False),
        )
        return True

    if not webhook_url:
        logger.error("send_alert called with empty webhook_url — skipping.")
        return False

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=15,
            headers={"Content-Type": "application/json"},
        )
        if response.ok:
            logger.info(
                "Alert sent for {sku} ({reason}) — HTTP {status}",
                sku=event.product_sku,
                reason=event.reason,
                status=response.status_code,
            )
            return True
        else:
            logger.warning(
                "Alert webhook returned HTTP {status} for {sku}: {body}",
                status=response.status_code,
                sku=event.product_sku,
                body=response.text[:200],
            )
            return False
    except requests.exceptions.Timeout:
        logger.error(
            "Timeout sending alert for {sku} to {url}",
            sku=event.product_sku,
            url=webhook_url,
        )
        return False
    except requests.exceptions.RequestException as exc:
        logger.error(
            "Failed to send alert for {sku}: {exc}",
            sku=event.product_sku,
            exc=exc,
        )
        return False
