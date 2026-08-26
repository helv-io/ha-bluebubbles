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

    async def async_send_text(
        self,
        chat_guid: str,
        message: str,
        *,
        method: str = "apple-script",
    ) -> dict[str, Any]:
        """Send text to an existing chat via /api/v1/message/text."""
        url = f"{self._host}/api/v1/message/text"
        payload = {
            "chatGuid": chat_guid,
            "tempGuid": f"temp-{uuid.uuid4()}",
            "message": message,
            "method": method,
        }

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

    async def async_list_webhooks(self) -> list[dict[str, Any]]:
        """List webhooks registered with the BlueBubbles server."""
        url = f"{self._host}/api/v1/webhook"
        try:
            async with self._session.get(
                url, params=self._params, ssl=self._ssl
            ) as response:
                payload = await async_parse_response(
                    response,
                    password=self._password,
                    context="BlueBubbles list webhooks",
                )
        except HomeAssistantError:
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Error listing BlueBubbles webhooks: %s", err)
            raise HomeAssistantError(
                f"Cannot connect to BlueBubbles server: {err}"
            ) from err

        data = payload.get("data")
        if data is None:
            return []
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    async def async_create_webhook(
        self, webhook_url: str, events: list[str]
    ) -> dict[str, Any]:
        """Register a webhook URL with the BlueBubbles server."""
        url = f"{self._host}/api/v1/webhook"
        payload = {"url": webhook_url, "events": events}
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
                    context="BlueBubbles create webhook",
                )
        except HomeAssistantError:
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Error creating BlueBubbles webhook: %s", err)
            raise HomeAssistantError(
                f"Cannot connect to BlueBubbles server: {err}"
            ) from err

    async def async_delete_webhook(self, webhook_id: str | int) -> dict[str, Any]:
        """Delete a webhook registration from the BlueBubbles server."""
        url = f"{self._host}/api/v1/webhook/{webhook_id}"
        try:
            async with self._session.delete(
                url, params=self._params, ssl=self._ssl
            ) as response:
                return await async_parse_response(
                    response,
                    password=self._password,
                    context="BlueBubbles delete webhook",
                )
        except HomeAssistantError:
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Error deleting BlueBubbles webhook: %s", err)
            raise HomeAssistantError(
                f"Cannot connect to BlueBubbles server: {err}"
            ) from err


def normalize_inbound_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a BlueBubbles webhook payload into trigger-friendly event data.

    Returns None when the payload is not a usable new-message event.
    """
    event_type = payload.get("type")
    data = payload.get("data")

    # Some servers wrap the message under data; others may POST the message body
    # directly. Accept both shapes.
    if isinstance(data, dict) and event_type:
        message = data
    elif isinstance(payload.get("guid"), str) or isinstance(payload.get("text"), str):
        message = payload
        event_type = event_type or "new-message"
    else:
        return None

    if event_type not in (None, "new-message", "message"):
        return None

    if not isinstance(message, dict):
        return None

    handle = message.get("handle") if isinstance(message.get("handle"), dict) else {}
    chats = message.get("chats") if isinstance(message.get("chats"), list) else []
    chat = chats[0] if chats and isinstance(chats[0], dict) else {}

    attachments_raw = message.get("attachments")
    attachments: list[dict[str, Any]] = []
    if isinstance(attachments_raw, list):
        for item in attachments_raw:
            if not isinstance(item, dict):
                continue
            attachments.append(
                {
                    "guid": item.get("guid"),
                    "transfer_name": item.get("transferName")
                    or item.get("transfer_name")
                    or item.get("name"),
                    "mime_type": item.get("mimeType") or item.get("mime_type"),
                    "total_bytes": item.get("totalBytes") or item.get("total_bytes"),
                }
            )

    sender = handle.get("address") or message.get("sender") or ""
    sender_name = (
        handle.get("displayName")
        or handle.get("display_name")
        or chat.get("displayName")
        or ""
    )

    date_created = message.get("dateCreated") or message.get("date_created")
    timestamp: str | int | None
    if isinstance(date_created, (int, float)):
        timestamp = int(date_created)
    elif isinstance(date_created, str):
        timestamp = date_created
    else:
        timestamp = None

    text = message.get("text")
    if text is None:
        text = ""
    else:
        text = str(text)

    return {
        "text": text,
        "sender": str(sender) if sender else "",
        "sender_name": str(sender_name) if sender_name else "",
        "chat_guid": chat.get("guid") or message.get("chatGuid") or "",
        "chat_identifier": chat.get("chatIdentifier")
        or chat.get("chat_identifier")
        or "",
        "message_guid": message.get("guid") or "",
        "is_from_me": bool(message.get("isFromMe") or message.get("is_from_me")),
        "timestamp": timestamp,
        "attachments": attachments,
        "service": handle.get("service") or message.get("service") or "",
        "subject": message.get("subject") or "",
    }
