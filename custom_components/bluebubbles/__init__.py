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

    async def fetch_and_update_private_api():
        conf = entry.data
        host = conf[CONF_HOST]
        password = conf[CONF_PASSWORD]
        ssl = conf[CONF_SSL]
        url = f"{host}/api/v1/server/info"
        params = {"password": password}

        try:
            async with aiohttp.ClientSession() as session, session.get(
                url, params=params, ssl=ssl
            ) as response:
                response.raise_for_status()
                json_data = await response.json()
                if json_data.get("status") == 200:
                    new_private_api = json_data["data"]["private_api"]
                    if new_private_api != conf.get("private_api", False):
                        new_data = dict(conf)  # Copy to avoid mutating original
                        new_data["private_api"] = new_private_api
                        hass.config_entries.async_update_entry(entry, data=new_data)
                        _LOGGER.debug("Updated private_api to %s", new_private_api)
        except aiohttp.ClientError as err:
            _LOGGER.warning("Failed to update server info: %s", err)

    await fetch_and_update_private_api()

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

        if not private_api and len(addresses) > 1:
            raise ValueError("Sending to multiple addresses is only supported when Private API is enabled on your BlueBubbles server. Please use a single address or enable Private API for group messaging.")

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