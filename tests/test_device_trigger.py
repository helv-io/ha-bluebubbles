"""Tests for BlueBubbles device triggers."""

from __future__ import annotations

from homeassistant.components import automation
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.bluebubbles import device_trigger
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
    MATCH_TYPE_REGEX,
    TRIGGER_TYPE_MESSAGE_RECEIVED,
    TRIGGER_TYPE_PHRASE_RECEIVED,
)

MOCK_HOST = "http://127.0.0.1:1234"
MOCK_PASSWORD = "test-password"
WEBHOOK_ID = "trigger-webhook"


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
    device = device_registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    return entry, device.id


async def test_async_get_triggers(hass: HomeAssistant, aioclient_mock) -> None:
    """Device exposes message_received and phrase_received triggers."""
    _entry, device_id = await _setup_entry(hass, aioclient_mock)
    triggers = await device_trigger.async_get_triggers(hass, device_id)
    types = {trigger[CONF_TYPE] for trigger in triggers}
    assert types == {TRIGGER_TYPE_MESSAGE_RECEIVED, TRIGGER_TYPE_PHRASE_RECEIVED}


async def test_device_triggers_listed_when_inbound_disabled(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Device triggers stay discoverable when inbound webhooks are off."""
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

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    triggers = await device_trigger.async_get_triggers(hass, device.id)
    assert {trigger[CONF_TYPE] for trigger in triggers} == {
        TRIGGER_TYPE_MESSAGE_RECEIVED,
        TRIGGER_TYPE_PHRASE_RECEIVED,
    }


async def test_async_validate_trigger_config(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """TRIGGER_SCHEMA validation accepts a message_received device trigger."""
    _entry, device_id = await _setup_entry(hass, aioclient_mock)
    validated = await device_trigger.async_validate_trigger_config(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: TRIGGER_TYPE_MESSAGE_RECEIVED,
        },
    )
    assert validated[CONF_TYPE] == TRIGGER_TYPE_MESSAGE_RECEIVED


async def test_phrase_capabilities_include_match_fields(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Phrase trigger capabilities expose phrase + match_type."""
    _entry, device_id = await _setup_entry(hass, aioclient_mock)
    caps = await device_trigger.async_get_trigger_capabilities(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: TRIGGER_TYPE_PHRASE_RECEIVED,
        },
    )
    assert "extra_fields" in caps


async def test_message_received_trigger_fires(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """message_received device trigger runs automations on inbound events."""
    _entry, device_id = await _setup_entry(hass, aioclient_mock)
    calls = async_mock_service(hass, "test", "automation")

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        CONF_PLATFORM: "device",
                        CONF_DOMAIN: DOMAIN,
                        CONF_DEVICE_ID: device_id,
                        CONF_TYPE: TRIGGER_TYPE_MESSAGE_RECEIVED,
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
    # Jinja may coerce +1555... to an int; chat_guid proves structured trigger data.
    assert "15551234567" in str(calls[0].data["sender"])
    assert calls[0].data["chat_guid"] == "any;-;+15551234567"


async def test_phrase_received_contains_and_regex(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """phrase_received supports contains and regex match types."""
    _entry, device_id = await _setup_entry(hass, aioclient_mock)
    calls = async_mock_service(hass, "test", "automation")

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "alias": "contains",
                    "trigger": {
                        CONF_PLATFORM: "device",
                        CONF_DOMAIN: DOMAIN,
                        CONF_DEVICE_ID: device_id,
                        CONF_TYPE: TRIGGER_TYPE_PHRASE_RECEIVED,
                        CONF_PHRASE: "bill",
                        CONF_MATCH_TYPE: MATCH_TYPE_CONTAINS,
                    },
                    "action": {"service": "test.automation", "data": {"which": "contains"}},
                },
                {
                    "alias": "regex",
                    "trigger": {
                        CONF_PLATFORM: "device",
                        CONF_DOMAIN: DOMAIN,
                        CONF_DEVICE_ID: device_id,
                        CONF_TYPE: TRIGGER_TYPE_PHRASE_RECEIVED,
                        CONF_PHRASE: r"^doorbell:\s*(.+)$",
                        CONF_MATCH_TYPE: MATCH_TYPE_REGEX,
                    },
                    "action": {"service": "test.automation", "data": {"which": "regex"}},
                },
                {
                    "alias": "exact",
                    "trigger": {
                        CONF_PLATFORM: "device",
                        CONF_DOMAIN: DOMAIN,
                        CONF_DEVICE_ID: device_id,
                        CONF_TYPE: TRIGGER_TYPE_PHRASE_RECEIVED,
                        CONF_PHRASE: "Status",
                        CONF_MATCH_TYPE: MATCH_TYPE_EXACT,
                    },
                    "action": {"service": "test.automation", "data": {"which": "exact"}},
                },
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

    await _fire("Send me the bill please")
    await _fire("Doorbell: One sec")
    await _fire("status")
    await _fire("no match here")

    which = [call.data["which"] for call in calls]
    assert which == ["contains", "regex", "exact"]


def test_phrase_matches_helpers() -> None:
    """Unit-test phrase matching edge cases."""
    assert device_trigger._phrase_matches("Hello BILL", "bill", MATCH_TYPE_CONTAINS)
    assert device_trigger._phrase_matches("Status", "status", MATCH_TYPE_EXACT)
    assert not device_trigger._phrase_matches("Status now", "status", MATCH_TYPE_EXACT)
    assert device_trigger._phrase_matches("code 123", r"\d+", MATCH_TYPE_REGEX)
    assert not device_trigger._phrase_matches("abc", r"[", MATCH_TYPE_REGEX)
