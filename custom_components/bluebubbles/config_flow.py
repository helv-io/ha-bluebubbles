"""Config flow for BlueBubbles integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BlueBubblesApi
from .const import CONF_PASSWORD, CONF_SSL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
        ),
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_SSL, default=False): selector.BooleanSelector(),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BlueBubbles."""

    VERSION = 1

    async def async_step_user(
        self, user_input=None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            password = user_input[CONF_PASSWORD]
            ssl = user_input[CONF_SSL]

            try:
                session = async_get_clientsession(self.hass, verify_ssl=ssl)
                api = BlueBubblesApi(host, password, ssl, session)
                json_data = await api.async_get_server_info()
                data = json_data["data"]
                private_api = data["private_api"]
                detected_imessage = data["detected_imessage"]
                entry_data = dict(user_input)
                entry_data["private_api"] = private_api
                _LOGGER.debug("Successfully connected to BlueBubbles")
                return self.async_create_entry(
                    title=detected_imessage, data=entry_data
                )
            except HomeAssistantError as err:
                _LOGGER.error("Error connecting to BlueBubbles: %s", err)
                errors["base"] = "cannot_connect"
            except (KeyError, TypeError, ValueError) as err:
                _LOGGER.error("Unexpected BlueBubbles server info payload: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:  # noqa: BLE001 - surface unexpected setup failures
                _LOGGER.error("Unexpected error: %s", err)
                errors["base"] = "unknown"

            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors=errors,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors={},
        )
