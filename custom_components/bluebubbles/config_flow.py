"""Config flow for BlueBubbles integration."""
import logging

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.helpers import selector

from .const import CONF_COUNTRY_CODE, CONF_PASSWORD, CONF_SSL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BlueBubbles."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""

        if user_input is not None:
            errors = {}

            host = user_input[CONF_HOST]
            password = user_input[CONF_PASSWORD]
            ssl = user_input[CONF_SSL]
            url = f"{host}/api/v1/ping"
            params = {"password": password}

            try:
                async with aiohttp.ClientSession() as session, session.get(
                    url,
                    params=params,
                    ssl=ssl
                ) as response:
                    response.raise_for_status()
                    _LOGGER.debug("Successfully connected to BlueBubbles")
                    return self.async_create_entry(title="BlueBubbles", data=user_input)
            except aiohttp.ClientError as err:
                _LOGGER.error("Error connecting to BlueBubbles: %s", err)
                errors["base"] = "cannot_connect"

            # If you want to catch other exceptions (e.g., timeouts separately), add more except blocks here

            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_HOST): selector.TextSelector(
                            selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                        ),
                        vol.Required(CONF_PASSWORD): selector.TextSelector(
                            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                        ),
                        vol.Optional(CONF_SSL, default=False): selector.BooleanSelector(),
                        vol.Optional(CONF_COUNTRY_CODE, default="1"): selector.TextSelector(),
                    }
                ),
                errors=errors,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                    ),
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(CONF_SSL, default=False): selector.BooleanSelector(),
                    vol.Optional(CONF_COUNTRY_CODE, default="1"): selector.TextSelector(),
                }
            ),
            errors={},
        )
