"""Tests for BlueBubbles diagnostics redaction."""

from __future__ import annotations

import json

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bluebubbles.const import (
    CONF_ENABLE_INBOUND,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_WEBHOOK_ID,
    DOMAIN,
)
from custom_components.bluebubbles.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
)

MOCK_HOST = "http://127.0.0.1:1234"
MOCK_PASSWORD = "super-secret-bb-password"
WEBHOOK_ID = "diag-webhook-id"


async def test_diagnostics_redacts_password(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Diagnostics include host/flags/path/version but never the password."""
    aioclient_mock.get(
        f"{MOCK_HOST}/api/v1/server/info",
        json={
            "status": 200,
            "data": {"private_api": True, "detected_imessage": "user@icloud.com"},
        },
    )
    assert await async_setup_component(hass, "diagnostics", {})

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PASSWORD: MOCK_PASSWORD,
            CONF_SSL: False,
            "private_api": True,
        },
        options={
            CONF_ENABLE_INBOUND: True,
            CONF_WEBHOOK_ID: WEBHOOK_ID,
            "auto_register_webhook": False,
            "webhook_local_only": True,
            "include_from_me": False,
            "allowed_handles": "",
        },
        title="user@icloud.com",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["inbound_enabled"] is True
    assert result["webhook_path"] == f"/api/webhook/{WEBHOOK_ID}"
    assert result["private_api"] is True
    assert result["integration_version"] == "0.7.0"

    config_data = result["config_entry"]["data"]
    assert config_data[CONF_HOST] == MOCK_HOST
    assert config_data[CONF_PASSWORD] == async_redact_data(
        {CONF_PASSWORD: MOCK_PASSWORD}, TO_REDACT
    )[CONF_PASSWORD]
    assert CONF_WEBHOOK_ID not in result["config_entry"]["options"]

    serialized = json.dumps(result)
    assert MOCK_PASSWORD not in serialized
    assert "password" in serialized  # key present, value redacted
