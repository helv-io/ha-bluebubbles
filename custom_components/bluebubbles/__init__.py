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

        services = ["iMessage", "RCS", "SMS"]
        url = f"{host}/api/v1/message/text"
        params = {"password": password}
        temp_guid = str(uuid.uuid4())

        last_error = None
        for service in services:
            chat_guid = f"{service};-;{number}"
            payload = {"chatGuid": chat_guid, "message": message, "tempGuid": temp_guid}

            try:
                async with aiohttp.ClientSession() as session, session.post(
                    url,
                    json=payload,
                    params=params,
                    ssl=ssl
                ) as response:
                    if response.status == 200:
                        _LOGGER.debug(f"Message sent successfully using {service}")
                        return
                    else:
                        _LOGGER.warning(f"Failed to send using {service}, status: {response.status}")
                        last_error = aiohttp.ClientError(f"Status {response.status}")
            except aiohttp.ClientError as err:
                _LOGGER.warning(f"Error sending using {service}: {err}")
                last_error = err

        if last_error:
            _LOGGER.error("All send attempts failed")
            raise last_error

    hass.services.async_register(DOMAIN, "send_imessage", send_imessage)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.services.async_remove(DOMAIN, "send_imessage")
    hass.data[DOMAIN].pop(entry.entry_id)
    return True