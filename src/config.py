"""
Configuration loader for the price monitor application.

Loads config.yaml (structure) and .env (secrets), then interpolates
${VAR_NAME} placeholders in YAML string values with their env-var equivalents.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.models import Product

# ---------------------------------------------------------------------------
# Nested config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class GeneralConfig:
    user_agents_rotation: bool = True
    request_timeout_seconds: int = 30
    max_retries: int = 3
    retry_backoff_seconds: int = 5
    parallel_requests: bool = False


@dataclass
class StoreConfig:
    enabled: bool = True
    rate_limit_seconds: int = 3
    use_api: bool = False
    use_scraperapi: bool = False


@dataclass
class AlertTriggers:
    price_drop_percent: float = 5.0
    below_target: bool = True
    back_in_stock: bool = True


@dataclass
class AlertConfig:
    webhook_url: str = ""
    triggers: AlertTriggers = field(default_factory=AlertTriggers)
    cooldown_minutes: int = 360


@dataclass
class AppConfig:
    general: GeneralConfig
    stores: dict[str, StoreConfig]
    products: list[Product]
    alerts: AlertConfig


# ---------------------------------------------------------------------------
# Env-var interpolation
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _interpolate(value: Any) -> Any:
    """Recursively replace ${VAR_NAME} in string values with env-var contents."""
    if isinstance(value, str):

        def _replace(match: re.Match) -> str:
            var = match.group(1)
            env_value = os.environ.get(var)
            if env_value is None:
                # Leave the placeholder intact so callers can detect it
                return match.group(0)
            return env_value

        return _PLACEHOLDER_RE.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _parse_general(raw: dict[str, Any]) -> GeneralConfig:
    return GeneralConfig(
        user_agents_rotation=bool(raw.get("user_agents_rotation", True)),
        request_timeout_seconds=int(raw.get("request_timeout_seconds", 30)),
        max_retries=int(raw.get("max_retries", 3)),
        retry_backoff_seconds=int(raw.get("retry_backoff_seconds", 5)),
        parallel_requests=bool(raw.get("parallel_requests", False)),
    )


def _parse_stores(raw: dict[str, Any]) -> dict[str, StoreConfig]:
    result: dict[str, StoreConfig] = {}
    for name, cfg in raw.items():
        result[name] = StoreConfig(
            enabled=bool(cfg.get("enabled", True)),
            rate_limit_seconds=int(cfg.get("rate_limit_seconds", 3)),
            use_api=bool(cfg.get("use_api", False)),
            use_scraperapi=bool(cfg.get("use_scraperapi", False)),
        )
    return result


def _parse_products(raw: list[dict[str, Any]]) -> list[Product]:
    products: list[Product] = []
    for item in raw:
        if "sku" not in item:
            raise ValueError(f"Product entry missing 'sku': {item!r}")
        if "target_price" not in item:
            raise ValueError(f"Product '{item['sku']}' missing 'target_price'")
        products.append(Product.from_dict(item))
    return products


def _parse_alerts(raw: dict[str, Any]) -> AlertConfig:
    webhook_url = str(raw.get("webhook_url", ""))
    triggers_raw = raw.get("triggers", {})
    triggers = AlertTriggers(
        price_drop_percent=float(triggers_raw.get("price_drop_percent", 5.0)),
        below_target=bool(triggers_raw.get("below_target", True)),
        back_in_stock=bool(triggers_raw.get("back_in_stock", True)),
    )
    return AlertConfig(
        webhook_url=webhook_url,
        triggers=triggers,
        cooldown_minutes=int(raw.get("cooldown_minutes", 360)),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(
    config_path: str | Path = "config.yaml",
    env_path: str | Path = ".env",
) -> AppConfig:
    """
    Load and validate application configuration.

    Parameters
    ----------
    config_path:
        Path to the YAML config file (default: ``config.yaml`` in cwd).
    env_path:
        Path to the ``.env`` file (default: ``.env`` in cwd). Missing file is
        silently ignored so environment variables can be injected externally.

    Raises
    ------
    FileNotFoundError
        If *config_path* does not exist.
    ValueError
        If required sections are missing or contain invalid values.
    """
    # Load .env (silently ignore if absent — env may be set externally)
    load_dotenv(dotenv_path=env_path, override=False)

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}. "
            "Copy config.example.yaml to config.yaml and customise it."
        )

    with config_path.open("r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    # Interpolate ${VAR} placeholders after env is loaded
    raw = _interpolate(raw)

    # Required top-level keys
    for key in ("general", "stores", "products", "alerts"):
        if key not in raw:
            raise ValueError(
                f"Required top-level key '{key}' missing from {config_path}."
            )

    if not isinstance(raw["products"], list) or len(raw["products"]) == 0:
        raise ValueError("'products' must be a non-empty list in config.yaml.")

    general = _parse_general(raw["general"])
    stores = _parse_stores(raw["stores"])
    products = _parse_products(raw["products"])
    alerts = _parse_alerts(raw["alerts"])

    # Warn if webhook URL was not resolved (still contains placeholder)
    if "${" in alerts.webhook_url:
        import warnings

        warnings.warn(
            "alerts.webhook_url still contains an unresolved placeholder. "
            "Set N8N_WEBHOOK_URL in your .env or environment.",
            stacklevel=2,
        )

    return AppConfig(
        general=general,
        stores=stores,
        products=products,
        alerts=alerts,
    )
