"""Tests for inbound webhook handling and normalization."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bluebubbles.api import (
    BlueBubblesApi,
    normalize_inbound_message,
)
from custom_components.bluebubbles.const import (
    CONF_ALLOWED_HANDLES,
    CONF_AUTO_REGISTER_WEBHOOK,
    CONF_ENABLE_INBOUND,
    CONF_HOST,
    CONF_INCLUDE_FROM_ME,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_LOCAL_ONLY,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
)

MOCK_HOST = "http://127.0.0.1:1234"
MOCK_PASSWORD = "test-password"
WEBHOOK_ID = "test-webhook-id"


def _sample_payload(*, text: str = "hello", is_from_me: bool = False) -> dict:
    return {
        "type": "new-message",
        "data": {
            "guid": "msg-guid-1",
            "text": text,
            "isFromMe": is_from_me,
            "dateCreated": 1772642539012,
            "handle": {
                "address": "+15551234567",
                "service": "iMessage",
            },
            "attachments": [
                {
                    "guid": "att-1",
                    "transferName": "photo.jpg",
                    "mimeType": "image/jpeg",
                    "totalBytes": 1234,
                }
            ],
            "chats": [
                {
                    "chatIdentifier": "+15551234567",
                    "guid": "any;-;+15551234567",
                    "displayName": "",
                }
            ],
        },
    }


def test_normalize_inbound_message_extracts_fields() -> None:
    """Webhook payloads become trigger-friendly dicts."""
    result = normalize_inbound_message(_sample_payload(text="Ping"))
    assert result is not None
    assert result["text"] == "Ping"
    assert result["sender"] == "+15551234567"
    assert result["chat_guid"] == "any;-;+15551234567"
    assert result["message_guid"] == "msg-guid-1"
    assert result["is_from_me"] is False
    assert result["timestamp"] == 1772642539012
    assert result["attachments"][0]["transfer_name"] == "photo.jpg"
    assert result["service"] == "iMessage"


def test_normalize_inbound_message_ignores_other_types() -> None:
    """Non new-message events are ignored."""
    assert (
        normalize_inbound_message({"type": "typing-indicator", "data": {}}) is None
    )


@pytest.mark.asyncio
async def test_create_and_list_webhooks_api() -> None:
    """API client webhook helpers parse success payloads."""

    class FakeResponse:
        def __init__(self, payload):
            self.status = 200
            self._payload = payload

        async def text(self):
            import json

            return json.dumps(self._payload)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def __init__(self):
            self.calls = []

        def get(self, *args, **kwargs):
            self.calls.append(("get", args, kwargs))
            return FakeResponse(
                {
                    "status": 200,
                    "data": [{"id": 1, "url": "http://ha/api/webhook/x"}],
                }
            )

        def post(self, *args, **kwargs):
            self.calls.append(("post", args, kwargs))
            return FakeResponse({"status": 200, "data": {"id": 9}})

        def delete(self, *args, **kwargs):
            self.calls.append(("delete", args, kwargs))
            return FakeResponse({"status": 200, "data": True})

    session = FakeSession()
    api = BlueBubblesApi(MOCK_HOST, MOCK_PASSWORD, False, session)  # type: ignore[arg-type]

    listed = await api.async_list_webhooks()
    assert listed[0]["id"] == 1
    created = await api.async_create_webhook("http://ha/api/webhook/x", ["new-message"])
    assert created["data"]["id"] == 9
    await api.async_delete_webhook(9)
    assert [call[0] for call in session.calls] == ["get", "post", "delete"]


async def _setup_with_inbound(
    hass: HomeAssistant, aioclient_mock, *, options: dict | None = None
) -> MockConfigEntry:
    aioclient_mock.get(
        f"{MOCK_HOST}/api/v1/server/info",
        json={
            "status": 200,
            "message": "Success",
            "data": {"private_api": True, "detected_imessage": "user@icloud.com"},
        },
    )
    aioclient_mock.get(
        f"{MOCK_HOST}/api/v1/webhook",
        json={"status": 200, "data": []},
    )
    aioclient_mock.post(
        f"{MOCK_HOST}/api/v1/webhook",
        json={"status": 200, "data": {"id": 42}},
    )
    aioclient_mock.delete(
        f"{MOCK_HOST}/api/v1/webhook/42",
        json={"status": 200, "data": True},
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PASSWORD: MOCK_PASSWORD,
            CONF_SSL: False,
            "private_api": True,
        },
        options=options
        or {
            CONF_ENABLE_INBOUND: True,
            CONF_WEBHOOK_ID: WEBHOOK_ID,
            CONF_AUTO_REGISTER_WEBHOOK: True,
            CONF_WEBHOOK_LOCAL_ONLY: True,
            CONF_INCLUDE_FROM_ME: False,
            CONF_ALLOWED_HANDLES: "",
        },
        title="user@icloud.com",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.bluebubbles.inbound.webhook.async_generate_url",
        return_value=f"http://homeassistant.local:8123/api/webhook/{WEBHOOK_ID}",
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_inbound_fires_event(hass: HomeAssistant, aioclient_mock) -> None:
    """Inbound manager fires EVENT_MESSAGE_RECEIVED for new messages."""
    entry = await _setup_with_inbound(hass, aioclient_mock)
    runtime = hass.data[DOMAIN][entry.entry_id]

    events: list = []

    def _capture(event):
        events.append(event)

    hass.bus.async_listen(EVENT_MESSAGE_RECEIVED, _capture)

    await runtime.inbound.async_handle_payload(_sample_payload(text="Help me"))
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["text"] == "Help me"
    assert events[0].data["sender"] == "+15551234567"
    assert events[0].data["device_id"] == runtime.device_id


async def test_inbound_filters_from_me(hass: HomeAssistant, aioclient_mock) -> None:
    """Messages from me are ignored unless include_from_me is enabled."""
    entry = await _setup_with_inbound(hass, aioclient_mock)
    runtime = hass.data[DOMAIN][entry.entry_id]
    events: list = []
    hass.bus.async_listen(EVENT_MESSAGE_RECEIVED, lambda e: events.append(e))

    await runtime.inbound.async_handle_payload(
        _sample_payload(text="mine", is_from_me=True)
    )
    await hass.async_block_till_done()
    assert events == []


async def test_inbound_allowed_handles_filter(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """allowed_handles drops messages from other senders."""
    entry = await _setup_with_inbound(
        hass,
        aioclient_mock,
        options={
            CONF_ENABLE_INBOUND: True,
            CONF_WEBHOOK_ID: WEBHOOK_ID,
            CONF_AUTO_REGISTER_WEBHOOK: False,
            CONF_WEBHOOK_LOCAL_ONLY: True,
            CONF_INCLUDE_FROM_ME: False,
            CONF_ALLOWED_HANDLES: "+19998887777",
        },
    )
    runtime = hass.data[DOMAIN][entry.entry_id]
    events: list = []
    hass.bus.async_listen(EVENT_MESSAGE_RECEIVED, lambda e: events.append(e))

    await runtime.inbound.async_handle_payload(_sample_payload())
    await hass.async_block_till_done()
    assert events == []


async def test_unload_unregisters_webhook(hass: HomeAssistant, aioclient_mock) -> None:
    """Unloading the entry tears down the HA webhook listener."""
    entry = await _setup_with_inbound(
        hass,
        aioclient_mock,
        options={
            CONF_ENABLE_INBOUND: True,
            CONF_WEBHOOK_ID: WEBHOOK_ID,
            CONF_AUTO_REGISTER_WEBHOOK: False,
            CONF_WEBHOOK_LOCAL_ONLY: True,
            CONF_INCLUDE_FROM_ME: False,
            CONF_ALLOWED_HANDLES: "",
        },
    )

    with patch(
        "custom_components.bluebubbles.inbound.webhook.async_unregister"
    ) as unregister:
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        unregister.assert_called_once_with(hass, WEBHOOK_ID)

    assert entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_existing_send_still_works_with_inbound_disabled(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Outbound send_message keeps working when inbound is left off (default)."""
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

    aioclient_mock.post(
        f"{MOCK_HOST}/api/v1/chat/new",
        json={"status": 200, "message": "ok", "data": {"guid": "chat-1"}},
    )
    await hass.services.async_call(
        DOMAIN,
        "send_message",
        {"addresses": "+15551234567", "message": "hello"},
        blocking=True,
    )
