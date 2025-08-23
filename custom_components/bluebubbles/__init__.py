"""The BlueBubbles integration."""
import logging
import uuid

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import CONF_COUNTRY_CODE, CONF_HOST, CONF_PASSWORD, CONF_SSL, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BlueBubbles from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    async def send_imessage(service_call: ServiceCall) -> None:
        """Handle the send_imessage service."""
        conf = entry.data
        host = conf[CONF_HOST]
        password = conf[CONF_PASSWORD]
        ssl = conf[CONF_SSL]
        country_code = conf[CONF_COUNTRY_CODE]

        number = service_call.data.get("number")
        message = service_call.data.get("message")

        if not number.startswith("+"):
            number = f"+{country_code}{number}"

        chat_guid = f"iMessage;+;{number}"

        temp_guid = str(uuid.uuid4())

        url = f"{host}/api/v1/message/text"
        params = {"password": password}
        payload = {"chatGuid": chat_guid, "message": message, "tempGuid": temp_guid}

        try:
            async with aiohttp.ClientSession() as session, session.post(
                url,
                json=payload,
                params=params,
                ssl=ssl
            ) as response:
                response.raise_for_status()
                _LOGGER.debug("Message sent successfully")
        except aiohttp.ClientError as err:
            _LOGGER.error("Error sending message: %s", err)

    hass.services.async_register(DOMAIN, "send_imessage", send_imessage)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.services.async_remove(DOMAIN, "send_imessage")
    hass.data[DOMAIN].pop(entry.entry_id)
    return True
