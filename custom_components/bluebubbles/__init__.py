"""The BlueBubbles integration."""

from __future__ import annotations

import logging
import mimetypes
import re
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BlueBubblesApi
from .const import CONF_HOST, CONF_PASSWORD, CONF_SSL, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BlueBubbles from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    async def fetch_and_update_private_api() -> None:
        conf = entry.data
        host = conf[CONF_HOST]
        password = conf[CONF_PASSWORD]
        ssl = conf[CONF_SSL]
        try:
            session = async_get_clientsession(hass, verify_ssl=ssl)
            api = BlueBubblesApi(host, password, ssl, session)
            json_data = await api.async_get_server_info()
            new_private_api = json_data.get("data", {}).get("private_api")
            if new_private_api is None:
                return
            if new_private_api != conf.get("private_api", False):
                new_data = dict(conf)
                new_data["private_api"] = new_private_api
                hass.config_entries.async_update_entry(entry, data=new_data)
                _LOGGER.debug("Updated private_api to %s", new_private_api)
        except HomeAssistantError as err:
            _LOGGER.warning("Failed to update server info: %s", err)

    await fetch_and_update_private_api()

    async def send_message(service_call: ServiceCall) -> None:
        """Handle the send_message service."""
        conf = entry.data
        host = conf[CONF_HOST]
        password = conf[CONF_PASSWORD]
        ssl = conf[CONF_SSL]
        private_api = conf.get("private_api", False)

        addresses_str = str(service_call.data.get("addresses", "")).strip()
        message = str(service_call.data.get("message", "")).strip()
        attachment_path = str(service_call.data.get("attachment", "")).strip()
        media_url = str(service_call.data.get("media_url", "")).strip()

        if not addresses_str:
            raise HomeAssistantError("At least one address is required")
        if not message and not attachment_path and not media_url:
            raise HomeAssistantError(
                "Message, attachment, or media_url is required"
            )

        addresses = [
            n.strip() for n in re.split(r"[,;]", addresses_str) if n.strip()
        ]
        if not addresses:
            raise HomeAssistantError("No valid addresses provided")

        if not private_api and len(addresses) > 1:
            raise HomeAssistantError(
                "Sending to multiple addresses is only supported when Private "
                "API is enabled on your BlueBubbles server. Please use a single "
                "address or enable Private API for group messaging."
            )

        method = "private-api" if private_api else "apple-script"
        session = async_get_clientsession(hass, verify_ssl=ssl)
        api = BlueBubblesApi(host, password, ssl, session)

        chat_result = await api.async_create_chat(
            addresses,
            message=message or None,
            method=method,
        )

        if not attachment_path and not media_url:
            _LOGGER.debug("Message sent successfully")
            return

        chat_guid = (chat_result.get("data") or {}).get("guid")
        if not chat_guid:
            raise HomeAssistantError(
                "BlueBubbles did not return a chat GUID required to send "
                "attachments"
            )

        if attachment_path:
            if not hass.config.is_allowed_path(attachment_path):
                raise HomeAssistantError(
                    f"Path '{attachment_path}' is not allowed. Add it to "
                    "allowlist_external_dirs in configuration.yaml"
                )
            path = Path(attachment_path)
            if not await hass.async_add_executor_job(path.is_file):
                raise HomeAssistantError(
                    f"Attachment file not found: {attachment_path}"
                )
            file_data = await hass.async_add_executor_job(path.read_bytes)
            if not file_data:
                raise HomeAssistantError(
                    f"Attachment file is empty: {attachment_path}"
                )
            filename = path.name
            content_type = mimetypes.guess_type(filename)[0]
        else:
            file_data, filename, content_type = await api.async_download_media(
                media_url
            )

        await api.async_send_attachment(
            chat_guid,
            filename=filename,
            file_data=file_data,
            content_type=content_type,
            method=method,
        )
        _LOGGER.debug("Attachment '%s' sent successfully", filename)

    hass.services.async_register(DOMAIN, "send_message", send_message)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if hass.services.has_service(DOMAIN, "send_message"):
        hass.services.async_remove(DOMAIN, "send_message")
    if DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
