"""Tests for BlueBubbles options flow (inbound settings)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bluebubbles.const import (
    CONF_ENABLE_INBOUND,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_WEBHOOK_ID,
    DOMAIN,
)

MOCK_HOST = "http://127.0.0.1:1234"
MOCK_PASSWORD = "test-password"


async def test_options_flow_enables_inbound(hass: HomeAssistant) -> None:
    """Options flow can enable inbound and persist a webhook_id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PASSWORD: MOCK_PASSWORD,
            CONF_SSL: False,
            "private_api": True,
        },
        title="user@icloud.com",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert "webhook_path" in result["description_placeholders"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_ENABLE_INBOUND: True,
            "auto_register_webhook": False,
            "webhook_local_only": True,
            "include_from_me": False,
            "allowed_handles": "+15551234567",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_ENABLE_INBOUND] is True
    assert entry.options[CONF_WEBHOOK_ID]
    assert entry.options["allowed_handles"] == "+15551234567"
