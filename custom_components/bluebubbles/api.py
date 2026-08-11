"""BlueBubbles HTTP API helpers."""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import uuid
from typing import Any

import aiohttp
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

_SECRET_QUERY_RE = re.compile(
    r"((?:password|guid|token)=)([^&\s]+)", re.IGNORECASE
)
_SECRET_JSON_RE = re.compile(
    r'("(?:password|guid|token)"\s*:\s*")([^"]*)(")', re.IGNORECASE
)


def redact_secrets(text: str, extra_secrets: list[str] | None = None) -> str:
    """Redact passwords/tokens from loggable strings."""
    if not text:
        return text

    redacted = _SECRET_QUERY_RE.sub(r"\1***", text)
    redacted = _SECRET_JSON_RE.sub(r"\1***\3", redacted)

    for secret in extra_secrets or []:
        if secret:
            redacted = redacted.replace(secret, "***")

    return redacted


def extract_error_message(
    payload: Any, *, http_status: int | None = None
) -> str | None:
    """Extract an actionable error message from a BlueBubbles JSON body."""
    if not isinstance(payload, dict):
        if http_status is not None and http_status >= 400:
            return f"BlueBubbles request failed (HTTP {http_status})"
        return None

    detail: str | None = None
    error = payload.get("error")

    if isinstance(error, dict):
        for key in ("message", "error"):
            value = error.get(key)
            if value:
                detail = str(value)
                break
        if detail is None and error.get("type"):
            detail = str(error["type"])
    elif isinstance(error, str) and error.strip():
        detail = error.strip()

    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        if detail and message.strip() not in detail:
            detail = f"{message.strip()}: {detail}"
        elif detail is None:
            detail = message.strip()

    api_status = payload.get("status")
    if detail is None and isinstance(api_status, int) and api_status >= 400:
        detail = f"BlueBubbles API status {api_status}"

    if detail is None:
        if http_status is not None and http_status >= 400:
            return f"BlueBubbles request failed (HTTP {http_status})"
        return None

    if http_status is not None and http_status >= 400:
        return f"{detail} (HTTP {http_status})"
    return detail


def _payload_indicates_error(payload: dict[str, Any], http_status: int) -> bool:
    """Return True when the HTTP status or BlueBubbles body indicates failure."""
    if http_status >= 400:
        return True

    api_status = payload.get("status")
    if isinstance(api_status, int) and api_status >= 400:
        return True

    # Some failure payloads omit a high status but still include an error object.
    if payload.get("error") and api_status not in (None, 200):
        return True

    return False


async def async_parse_response(
    response: aiohttp.ClientResponse,
    *,
    password: str | None = None,
    context: str = "BlueBubbles request",
) -> dict[str, Any]:
    """Read and validate a BlueBubbles response, raising HomeAssistantError on failure."""
    raw = await response.text()
    safe_body = redact_secrets(raw, [password] if password else None)

    payload: Any
    if not raw:
        payload = {}
    else:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as err:
            _LOGGER.error(
                "%s returned non-JSON (HTTP %s): %s",
                context,
                response.status,
                safe_body[:500],
            )
            raise HomeAssistantError(
                f"{context} failed (HTTP {response.status}): invalid JSON response"
            ) from err

    if not isinstance(payload, dict):
        _LOGGER.error(
            "%s returned unexpected JSON (HTTP %s): %s",
            context,
            response.status,
            safe_body[:500],
        )
        raise HomeAssistantError(
            f"{context} failed (HTTP {response.status}): unexpected response"
        )

    if _payload_indicates_error(payload, response.status):
        message = extract_error_message(payload, http_status=response.status) or (
            f"{context} failed (HTTP {response.status})"
        )
        _LOGGER.error("%s: %s; body=%s", context, message, safe_body[:500])
        raise HomeAssistantError(message)

    return payload


class BlueBubblesApi:
    """Minimal BlueBubbles REST client used by the integration."""

    def __init__(
        self,
        host: str,
        password: str,
        ssl: bool,
        session: aiohttp.ClientSession,
    ) -> None:
        self._host = host.rstrip("/")
        self._password = password
        self._ssl = ssl
        self._session = session

    @property
    def _params(self) -> dict[str, str]:
        return {"password": self._password}

    async def async_get_server_info(self) -> dict[str, Any]:
        """Fetch /api/v1/server/info."""
        url = f"{self._host}/api/v1/server/info"
        try:
            async with self._session.get(
                url, params=self._params, ssl=self._ssl
            ) as response:
                return await async_parse_response(
                    response,
                    password=self._password,
                    context="BlueBubbles server info",
                )
        except HomeAssistantError:
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Error connecting to BlueBubbles: %s", err)
            raise HomeAssistantError(
                f"Cannot connect to BlueBubbles server: {err}"
            ) from err

    async def async_create_chat(
        self,
        addresses: list[str],
        *,
        message: str | None = None,
        method: str = "apple-script",
    ) -> dict[str, Any]:
        """Create or resolve a chat via /api/v1/chat/new, optionally sending text."""
        url = f"{self._host}/api/v1/chat/new"
        payload: dict[str, Any] = {
            "addresses": addresses,
            "method": method,
        }
        if message:
            payload["message"] = message

        try:
            async with self._session.post(
                url,
                json=payload,
                params=self._params,
                ssl=self._ssl,
            ) as response:
                return await async_parse_response(
                    response,
                    password=self._password,
                    context="BlueBubbles send message",
                )
        except HomeAssistantError:
            raise
        except aiohttp.ClientError as err:
            safe_payload = redact_secrets(
                json.dumps(payload), [self._password]
            )
            _LOGGER.error(
                "Error sending message: %s. Payload: %s", err, safe_payload
            )
            raise HomeAssistantError(
                f"Cannot connect to BlueBubbles server: {err}"
            ) from err

    async def async_send_attachment(
        self,
        chat_guid: str,
        *,
        filename: str,
        file_data: bytes,
        content_type: str | None = None,
        method: str = "apple-script",
    ) -> dict[str, Any]:
        """Send a file attachment via /api/v1/message/attachment."""
        url = f"{self._host}/api/v1/message/attachment"
        mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        form = aiohttp.FormData()
        form.add_field("chatGuid", chat_guid)
        form.add_field("tempGuid", f"temp-{uuid.uuid4()}")
        form.add_field("name", filename)
        form.add_field("method", method)
        form.add_field(
            "attachment",
            file_data,
            filename=filename,
            content_type=mime,
        )

        try:
            async with self._session.post(
                url,
                data=form,
                params=self._params,
                ssl=self._ssl,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                return await async_parse_response(
                    response,
                    password=self._password,
                    context="BlueBubbles send attachment",
                )
        except HomeAssistantError:
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Error sending attachment '%s': %s", filename, err)
            raise HomeAssistantError(
                f"Cannot connect to BlueBubbles server: {err}"
            ) from err

    async def async_download_media(self, media_url: str) -> tuple[bytes, str, str | None]:
        """Download media from a URL for use as an attachment."""
        try:
            async with self._session.get(
                media_url,
                ssl=self._ssl,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status >= 400:
                    body = await response.text()
                    _LOGGER.error(
                        "Failed to download media_url (HTTP %s): %s",
                        response.status,
                        redact_secrets(body, [self._password])[:500],
                    )
                    raise HomeAssistantError(
                        f"Failed to download media_url (HTTP {response.status})"
                    )
                data = await response.read()
                if not data:
                    raise HomeAssistantError("Downloaded media_url was empty")

                content_type = response.headers.get("Content-Type")
                if content_type and ";" in content_type:
                    content_type = content_type.split(";", 1)[0].strip()

                filename = media_url.rstrip("/").split("/")[-1] or "attachment"
                if "?" in filename:
                    filename = filename.split("?", 1)[0]
                if "." not in filename:
                    ext = mimetypes.guess_extension(content_type or "") or ".bin"
                    filename = f"{filename}{ext}"
                return data, filename, content_type
        except HomeAssistantError:
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Error downloading media_url: %s", err)
            raise HomeAssistantError(
                f"Cannot download media_url: {err}"
            ) from err
