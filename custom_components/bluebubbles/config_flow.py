"""The BlueBubbles integration."""
import logging
import re

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import CONF_HOST, CONF_PASSWORD, CONF_SSL, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BlueBubbles from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    async def send_message(service_call: ServiceCall) -> None:
        """Handle the send_message service."""
        conf = entry.data
        host = conf[CONF_HOST]
        password = conf[CONF_PASSWORD]
        ssl = conf[CONF_SSL]
        private_api = conf.get("private_api", False)

        addresses_str = service_call.data.get("addresses", "").strip()
        message = service_call.data.get("message", "").strip()

        if not addresses_str:
            raise ValueError("At least one address is required")
        if not message:
            raise ValueError("Message is required")

        # Split by , or ; and trim
        addresses = [n.strip() for n in re.split(r'[,;]', addresses_str) if n.strip()]

        if not addresses:
            raise ValueError("No valid addresses provided")

        url = f"{host}/api/v1/chat/new"
        params = {"password": password}
        method = "private-api" if private_api else "apple-script"
        payload = {"addresses": addresses, "message": message, "method": method}

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
            _LOGGER.error("Error sending message: %s. Payload: %s", err, payload)
            raise

    hass.services.async_register(DOMAIN, "send_message", send_message)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.services.async_remove(DOMAIN, "send_message")
    hass.data[DOMAIN].pop(entry.entry_id)
    return True