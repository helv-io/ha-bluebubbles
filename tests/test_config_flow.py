"""Tests for the BlueBubbles config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.bluebubbles.const import CONF_PASSWORD, CONF_SSL, DOMAIN

MOCK_HOST = "http://127.0.0.1:1234"
MOCK_PASSWORD = "test-password"


async def test_user_flow_success(hass: HomeAssistant, aioclient_mock) -> None:
    """Test a successful config flow."""
    aioclient_mock.get(
        f"{MOCK_HOST}/api/v1/server/info",
        json={
            "status": 200,
            "message": "Success",
            "data": {
                "private_api": True,
                "detected_imessage": "user@icloud.com",
            },
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    with patch.object(
        hass.config_entries,
        "async_setup",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: MOCK_HOST,
                CONF_PASSWORD: MOCK_PASSWORD,
                CONF_SSL: False,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "user@icloud.com"
    assert result["data"][CONF_HOST] == MOCK_HOST
    assert result["data"][CONF_PASSWORD] == MOCK_PASSWORD
    assert result["data"]["private_api"] is True


async def test_user_flow_cannot_connect(hass: HomeAssistant, aioclient_mock) -> None:
    """Test config flow failure when BlueBubbles returns an API error."""
    aioclient_mock.get(
        f"{MOCK_HOST}/api/v1/server/info",
        status=401,
        json={
            "status": 401,
            "message": "Unauthorized",
            "error": {"message": "Invalid password"},
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: MOCK_HOST,
            CONF_PASSWORD: MOCK_PASSWORD,
            CONF_SSL: False,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"
