"""Tests for bluebubbles.send_message service paths."""

from __future__ import annotations

from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bluebubbles.const import CONF_HOST, CONF_PASSWORD, CONF_SSL, DOMAIN

MOCK_HOST = "http://127.0.0.1:1234"
MOCK_PASSWORD = "test-password"


def _mock_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PASSWORD: MOCK_PASSWORD,
            CONF_SSL: False,
            "private_api": True,
        },
        title="user@icloud.com",
    )


async def _setup_integration(hass: HomeAssistant, aioclient_mock) -> MockConfigEntry:
    aioclient_mock.get(
        f"{MOCK_HOST}/api/v1/server/info",
        json={
            "status": 200,
            "message": "Success",
            "data": {"private_api": True, "detected_imessage": "user@icloud.com"},
        },
    )
    entry = _mock_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_send_message_maps_api_error_to_homeassistant_error(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Users should see the BlueBubbles error text, not a bare ClientError."""
    await _setup_integration(hass, aioclient_mock)
    aioclient_mock.post(
        f"{MOCK_HOST}/api/v1/chat/new",
        status=400,
        json={
            "status": 400,
            "message": "You've made a bad request!",
            "error": {"message": "Handle is not registered with iMessage"},
        },
    )

    with pytest.raises(HomeAssistantError, match="Handle is not registered with iMessage") as err:
        await hass.services.async_call(
            DOMAIN,
            "send_message",
            {"addresses": "+15551234567", "message": "hello"},
            blocking=True,
        )

    assert "Unknown error" not in str(err.value)


async def test_send_message_attachment_happy_path(
    hass: HomeAssistant, aioclient_mock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Attachment path is uploaded after chat creation."""
    await _setup_integration(hass, aioclient_mock)

    image_path = tmp_path / "snapshot.jpg"
    image_path.write_bytes(b"fake-image-bytes")

    monkeypatch.setattr(hass.config, "is_allowed_path", lambda path: True)

    aioclient_mock.post(
        f"{MOCK_HOST}/api/v1/chat/new",
        json={
            "status": 200,
            "message": "Successfully created chat!",
            "data": {"guid": "iMessage;-;+15551234567"},
        },
    )
    aioclient_mock.post(
        f"{MOCK_HOST}/api/v1/message/attachment",
        json={
            "status": 200,
            "message": "Successfully sent attachment!",
            "data": {"guid": "message-guid"},
        },
    )

    await hass.services.async_call(
        DOMAIN,
        "send_message",
        {
            "addresses": "+15551234567",
            "message": "Front door",
            "attachment": str(image_path),
        },
        blocking=True,
    )

    # mock_calls entries are (method, url, data, headers); urls may include query params
    paths = [req[1].path for req in aioclient_mock.mock_calls]
    assert "/api/v1/chat/new" in paths
    assert "/api/v1/message/attachment" in paths


async def test_send_message_media_url_happy_path(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """media_url is downloaded and sent as an attachment."""
    await _setup_integration(hass, aioclient_mock)

    aioclient_mock.post(
        f"{MOCK_HOST}/api/v1/chat/new",
        json={
            "status": 200,
            "message": "Successfully created chat!",
            "data": {"guid": "iMessage;-;+15551234567"},
        },
    )
    aioclient_mock.get(
        "http://127.0.0.1/local/snap.jpg",
        content=b"remote-image",
        headers={"Content-Type": "image/jpeg"},
    )
    aioclient_mock.post(
        f"{MOCK_HOST}/api/v1/message/attachment",
        json={
            "status": 200,
            "message": "Successfully sent attachment!",
            "data": {"guid": "message-guid"},
        },
    )

    await hass.services.async_call(
        DOMAIN,
        "send_message",
        {
            "addresses": "+15551234567",
            "media_url": "http://127.0.0.1/local/snap.jpg",
        },
        blocking=True,
    )
