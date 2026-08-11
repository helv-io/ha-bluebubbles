"""Diagnostics support for BlueBubbles."""

from __future__ import annotations

from typing import Any

from homeassistant.components import webhook
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import (
    CONF_ENABLE_INBOUND,
    CONF_PASSWORD,
    CONF_WEBHOOK_ID,
    DEFAULT_ENABLE_INBOUND,
    DOMAIN,
)

TO_REDACT = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Includes host and options flags, but never the BlueBubbles password.
    Webhook identity is exposed as the relative path only (not the raw id).
    """
    integration = await async_get_integration(hass, DOMAIN)
    options = dict(entry.options)
    webhook_id = options.get(CONF_WEBHOOK_ID)
    webhook_path = (
        webhook.async_generate_path(webhook_id) if webhook_id else None
    )

    # Drop the raw webhook_id; the path is enough for support without the secret.
    safe_options = {
        key: value for key, value in options.items() if key != CONF_WEBHOOK_ID
    }

    return {
        "config_entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": safe_options,
        },
        "inbound_enabled": bool(
            options.get(CONF_ENABLE_INBOUND, DEFAULT_ENABLE_INBOUND)
        ),
        "webhook_path": webhook_path,
        "private_api": entry.data.get("private_api"),
        "integration_version": str(integration.version),
    }
