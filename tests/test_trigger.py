"""Tests for BlueBubbles integration triggers."""

from __future__ import annotations

from homeassistant.components import automation
from homeassistant.const import CONF_OPTIONS, CONF_PLATFORM
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.bluebubbles import trigger as bb_trigger
from custom_components.bluebubbles.const import (
    CONF_ENABLE_INBOUND,
    CONF_HOST,
    CONF_MATCH_TYPE,
    CONF_PASSWORD,
    CONF_PHRASE,
    CONF_SSL,
    CONF_WEBHOOK_ID,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
    MATCH_TYPE_CONTAINS,
    MATCH_TYPE_EXACT,
    TRIGGER_TYPE_MESSAGE_RECEIVED,
    TRIGGER_TYPE_PHRASE_RECEIVED,
)

MOCK_HOST = "http://127.0.0.1:1234"
MOCK_PASSWORD = "test-password"
WEBHOOK_ID = "integration-trigger-webhook"


async def _setup_entry(hass: HomeAssistant, aioclient_mock) -> tuple[MockConfigEntry, str]:
    aioclient_mock.get(
        f"{MOCK_HOST}/api/v1/server/info",
        json={
            "status": 200,
            "data": {"private_api": True, "detected_imessage": "user@icloud.com"},
        },
    )
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

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert device is not None
    return entry, device.id


async def test_async_get_triggers_registers_both_types(hass: HomeAssistant) -> None:
    """Integration trigger platform exposes message_received and phrase_received."""
    triggers = await bb_trigger.async_get_triggers(hass)
    assert set(triggers) == {
        TRIGGER_TYPE_MESSAGE_RECEIVED,
        TRIGGER_TYPE_PHRASE_RECEIVED,
    }


async def test_triggers_visible_when_inbound_disabled(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Trigger registration is not gated on enable_inbound."""
    aioclient_mock.get(
        f"{MOCK_HOST}/api/v1/server/info",
        json={
            "status": 200,
            "data": {"private_api": True, "detected_imessage": "user@icloud.com"},
        },
    )
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
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    triggers = await bb_trigger.async_get_triggers(hass)
    assert TRIGGER_TYPE_MESSAGE_RECEIVED in triggers
    assert TRIGGER_TYPE_PHRASE_RECEIVED in triggers


async def test_message_received_integration_trigger_fires(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """bluebubbles.message_received runs automations on inbound events."""
    _entry, device_id = await _setup_entry(hass, aioclient_mock)
    calls = async_mock_service(hass, "test", "automation")

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        CONF_PLATFORM: f"{DOMAIN}.{TRIGGER_TYPE_MESSAGE_RECEIVED}",
                    },
                    "action": {
                        "service": "test.automation",
                        "data": {
                            "text": "{{ trigger.text }}",
                            "sender": "{{ trigger.sender }}",
                            "chat_guid": "{{ trigger.chat_guid }}",
                        },
                    },
                }
            ]
        },
    )

    hass.bus.async_fire(
        EVENT_MESSAGE_RECEIVED,
        {
            "device_id": device_id,
            "text": "Front door",
            "sender": "+15551234567",
            "sender_name": "",
            "chat_guid": "any;-;+15551234567",
            "chat_identifier": "+15551234567",
            "message_guid": "m1",
            "is_from_me": False,
            "timestamp": 1,
            "attachments": [],
            "service": "iMessage",
            "subject": "",
        },
    )
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data["text"] == "Front door"
    assert "15551234567" in str(calls[0].data["sender"])
    assert calls[0].data["chat_guid"] == "any;-;+15551234567"


async def test_phrase_received_integration_trigger(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """bluebubbles.phrase_received supports contains matching via options."""
    _entry, device_id = await _setup_entry(hass, aioclient_mock)
    calls = async_mock_service(hass, "test", "automation")

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        CONF_PLATFORM: f"{DOMAIN}.{TRIGGER_TYPE_PHRASE_RECEIVED}",
                        CONF_OPTIONS: {
                            CONF_PHRASE: "bill",
                            CONF_MATCH_TYPE: MATCH_TYPE_CONTAINS,
                        },
                    },
                    "action": {
                        "service": "test.automation",
                        "data": {
                            "which": "hit",
                            "matched": "{{ trigger.matched_phrase }}",
                        },
                    },
                }
            ]
        },
    )

    async def _fire(text: str) -> None:
        hass.bus.async_fire(
            EVENT_MESSAGE_RECEIVED,
            {
                "device_id": device_id,
                "text": text,
                "sender": "+15551234567",
                "sender_name": "",
                "chat_guid": "any;-;+15551234567",
                "chat_identifier": "+15551234567",
                "message_guid": "m1",
                "is_from_me": False,
                "timestamp": 1,
                "attachments": [],
                "service": "iMessage",
                "subject": "",
            },
        )
        await hass.async_block_till_done()

    await _fire("nope")
    await _fire("Send me the bill please")
    assert len(calls) == 1
    assert calls[0].data["which"] == "hit"
    assert calls[0].data["matched"] == "bill"


async def test_phrase_validate_config_requires_phrase(hass: HomeAssistant) -> None:
    """phrase_received validation requires a phrase option."""
    cls = bb_trigger.TRIGGERS[TRIGGER_TYPE_PHRASE_RECEIVED]
    validated = await cls.async_validate_config(
        hass,
        {
            CONF_OPTIONS: {
                CONF_PHRASE: "Status",
                CONF_MATCH_TYPE: MATCH_TYPE_EXACT,
            }
        },
    )
    assert validated[CONF_OPTIONS][CONF_PHRASE] == "Status"
