"""The BlueBubbles integration."""

from __future__ import annotations

import logging
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BlueBubblesApi
from .const import CONF_HOST, CONF_PASSWORD, CONF_SSL, DOMAIN
from .inbound import InboundManager

_LOGGER = logging.getLogger(__name__)

# No entity platforms; device_trigger.py is discovered via the device automation
# integration when automations reference this domain's devices.
PLATFORMS: list[Platform] = []


@dataclass
class BlueBubblesRuntimeData:
    """Runtime objects for a BlueBubbles config entry."""

    api: BlueBubblesApi
    inbound: InboundManager
    device_id: str


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BlueBubbles from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass, verify_ssl=entry.data.get(CONF_SSL, False))
    api = BlueBubblesApi(
        entry.data[CONF_HOST],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_SSL, False),
        session,
    )

    async def fetch_and_update_private_api() -> None:
        conf = entry.data
        try:
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

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title or "BlueBubbles",
        manufacturer="BlueBubbles",
        model="iMessage Server",
        configuration_url=entry.data.get(CONF_HOST),
    )

    inbound = InboundManager(hass, entry, api, device_id=device.id)
    await inbound.async_start()

    hass.data[DOMAIN][entry.entry_id] = BlueBubblesRuntimeData(
        api=api,
        inbound=inbound,
        device_id=device.id,
    )

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
        send_session = async_get_clientsession(hass, verify_ssl=ssl)
        send_api = BlueBubblesApi(host, password, ssl, send_session)

        chat_result = await send_api.async_create_chat(
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
            file_data, filename, content_type = await send_api.async_download_media(
                media_url
            )

        await send_api.async_send_attachment(
            chat_guid,
            filename=filename,
            file_data=file_data,
            content_type=content_type,
            method=method,
        )
        _LOGGER.debug("Attachment '%s' sent successfully", filename)

    if not hass.services.has_service(DOMAIN, "send_message"):
        hass.services.async_register(DOMAIN, "send_message", send_message)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change (inbound enable/disable, filters, etc.)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and tear down inbound listeners/webhooks."""
    runtime: BlueBubblesRuntimeData | dict[str, Any] | None = hass.data.get(
        DOMAIN, {}
    ).pop(entry.entry_id, None)

    if isinstance(runtime, BlueBubblesRuntimeData):
        await runtime.inbound.async_stop()

    # single_config_entry integration, but keep the guard for safety
    remaining = hass.data.get(DOMAIN, {})
    if not remaining and hass.services.has_service(DOMAIN, "send_message"):
        hass.services.async_remove(DOMAIN, "send_message")

    return True
