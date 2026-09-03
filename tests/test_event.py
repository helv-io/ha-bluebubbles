"""Tests for the BlueBubbles event entity."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bluebubbles.const import (
    CONF_ENABLE_INBOUND,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_WEBHOOK_ID,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
    TRIGGER_TYPE_MESSAGE_RECEIVED,
)

MOCK_HOST = "http://127.0.0.1:1234"
MOCK_PASSWORD = "test-password"
WEBHOOK_ID = "event-entity-webhook"


async def _setup_entry(
    hass: HomeAssistant, aioclient_mock, *, enable_inbound: bool = True
) -> tuple[MockConfigEntry, str]:
    aioclient_mock.get(
        f"{MOCK_HOST}/api/v1/server/info",
        json={
            "status": 200,
            "data": {"private_api": True, "detected_imessage": "user@icloud.com"},
        },
    )
    options = {}
    if enable_inbound:
        options = {
            CONF_ENABLE_INBOUND: True,
            CONF_WEBHOOK_ID: WEBHOOK_ID,
            "auto_register_webhook": False,
            "webhook_local_only": True,
            "include_from_me": False,
            "allowed_handles": "",
        }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PASSWORD: MOCK_PASSWORD,
            CONF_SSL: False,
            "private_api": True,
        },
        options=options,
        title="user@icloud.com",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert device is not None
    return entry, device.id


async def test_event_entity_created_with_inbound_disabled(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Event entity exists even when inbound is left off (default)."""
    await _setup_entry(hass, aioclient_mock, enable_inbound=False)
    states = [
        state
        for state in hass.states.async_all("event")
        if "message" in state.entity_id
    ]
    assert len(states) == 1
    assert states[0].entity_id == "event.user_icloud_com_message"
    assert states[0].attributes.get("event_types") == [TRIGGER_TYPE_MESSAGE_RECEIVED]


async def test_event_entity_fires_on_inbound(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Inbound bus events update the event entity attributes."""
    _entry, device_id = await _setup_entry(hass, aioclient_mock)
    states = [state for state in hass.states.async_all("event") if "message" in state.entity_id]
    assert len(states) == 1
    entity_id = states[0].entity_id

    hass.bus.async_fire(
        EVENT_MESSAGE_RECEIVED,
        {
            "device_id": device_id,
            "text": "Hello event entity",
            "sender": "+15551234567",
            "sender_name": "Pat",
            "chat_guid": "any;-;+15551234567",
            "chat_identifier": "+15551234567",
            "message_guid": "m-event-1",
            "is_from_me": False,
            "timestamp": 99,
            "attachments": [],
            "service": "iMessage",
            "subject": "",
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes.get("event_type") == TRIGGER_TYPE_MESSAGE_RECEIVED
    assert state.attributes.get("text") == "Hello event entity"
    assert state.attributes.get("sender") == "+15551234567"
    assert state.attributes.get("chat_guid") == "any;-;+15551234567"
