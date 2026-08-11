"""Unit tests for BlueBubbles API helpers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.bluebubbles.api import (
    BlueBubblesApi,
    async_parse_response,
    extract_error_message,
    redact_secrets,
)


def test_redact_secrets_query_and_json() -> None:
    """Passwords in query strings and JSON are redacted."""
    text = (
        "POST /api?password=super-secret&token=abc123 "
        '{"password":"super-secret","guid":"abc123","ok":true}'
    )
    redacted = redact_secrets(text, extra_secrets=["super-secret"])
    assert "super-secret" not in redacted
    assert "abc123" not in redacted
    assert "password=***" in redacted
    assert '"password":"***"' in redacted


def test_extract_error_message_from_nested_error() -> None:
    """Nested BlueBubbles error objects yield actionable text."""
    payload = {
        "status": 400,
        "message": "You've made a bad request!",
        "error": {
            "type": "Validation Error",
            "message": "Attachment not provided or was empty!",
        },
    }
    message = extract_error_message(payload, http_status=400)
    assert message is not None
    assert "Attachment not provided or was empty!" in message
    assert "HTTP 400" in message


def test_extract_error_message_legacy_error_key() -> None:
    """Legacy error.error key is supported."""
    payload = {
        "status": 500,
        "message": "Server error",
        "error": {"type": "Server Error", "error": "iMessage helper crashed"},
    }
    message = extract_error_message(payload, http_status=500)
    assert message is not None
    assert "iMessage helper crashed" in message


@pytest.mark.asyncio
async def test_async_parse_response_raises_homeassistant_error() -> None:
    """API error bodies become HomeAssistantError with useful text."""
    response = MagicMock()
    response.status = 400
    response.text = AsyncMock(
        return_value=json.dumps(
            {
                "status": 400,
                "message": "Bad request",
                "error": {"message": "Invalid password"},
            }
        )
    )

    with pytest.raises(HomeAssistantError, match="Invalid password") as err:
        await async_parse_response(
            response, password="hunter2", context="BlueBubbles send message"
        )

    assert "Unknown error" not in str(err.value)
    assert not isinstance(err.value, aiohttp.ClientError)


@pytest.mark.asyncio
async def test_async_parse_response_success() -> None:
    """Successful payloads are returned unchanged."""
    payload = {"status": 200, "message": "ok", "data": {"guid": "chat-1"}}
    response = MagicMock()
    response.status = 200
    response.text = AsyncMock(return_value=json.dumps(payload))

    result = await async_parse_response(response, password="secret")
    assert result == payload


@pytest.mark.asyncio
async def test_create_chat_maps_api_error() -> None:
    """create_chat surfaces BlueBubbles JSON errors as HomeAssistantError."""

    class FakeResponse:
        status = 200

        async def text(self):
            return json.dumps(
                {
                    "status": 500,
                    "message": "Failed to send",
                    "error": {"message": "Private API is not enabled"},
                }
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def post(self, *args, **kwargs):
            return FakeResponse()

    api = BlueBubblesApi(
        "http://bb.local:1234",
        "secret-password",
        False,
        FakeSession(),  # type: ignore[arg-type]
    )

    with pytest.raises(HomeAssistantError, match="Private API is not enabled") as err:
        await api.async_create_chat(["+15551234567"], message="hi")

    assert not isinstance(err.value, aiohttp.ClientError)
