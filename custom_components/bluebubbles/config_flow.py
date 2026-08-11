"""Config flow for BlueBubbles integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import webhook
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BlueBubblesApi
from .const import (
    CONF_ALLOWED_HANDLES,
    CONF_AUTO_REGISTER_WEBHOOK,
    CONF_ENABLE_INBOUND,
    CONF_INCLUDE_FROM_ME,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_LOCAL_ONLY,
    DEFAULT_AUTO_REGISTER_WEBHOOK,
    DEFAULT_ENABLE_INBOUND,
    DEFAULT_INCLUDE_FROM_ME,
    DEFAULT_WEBHOOK_LOCAL_ONLY,
    DOMAIN,
)

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
        self, user_input: dict[str, Any] | None = None
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
                _LOGGER.error(
                    "Unexpected BlueBubbles server info payload: %s", err
                )
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

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Return the options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle BlueBubbles options (inbound messaging)."""

    def __init__(self) -> None:
        """Initialize options flow state."""
        self._webhook_id: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage inbound messaging options."""
        current = self.config_entry.options
        if self._webhook_id is None:
            self._webhook_id = current.get(CONF_WEBHOOK_ID) or webhook.async_generate_id()
        webhook_path = webhook.async_generate_path(self._webhook_id)

        if user_input is not None:
            options = {
                CONF_ENABLE_INBOUND: user_input.get(
                    CONF_ENABLE_INBOUND, DEFAULT_ENABLE_INBOUND
                ),
                CONF_AUTO_REGISTER_WEBHOOK: user_input.get(
                    CONF_AUTO_REGISTER_WEBHOOK, DEFAULT_AUTO_REGISTER_WEBHOOK
                ),
                CONF_WEBHOOK_LOCAL_ONLY: user_input.get(
                    CONF_WEBHOOK_LOCAL_ONLY, DEFAULT_WEBHOOK_LOCAL_ONLY
                ),
                CONF_INCLUDE_FROM_ME: user_input.get(
                    CONF_INCLUDE_FROM_ME, DEFAULT_INCLUDE_FROM_ME
                ),
                CONF_ALLOWED_HANDLES: (
                    str(user_input.get(CONF_ALLOWED_HANDLES) or "").strip()
                ),
                CONF_WEBHOOK_ID: self._webhook_id,
            }
            return self.async_create_entry(title="", data=options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_INBOUND,
                    default=current.get(
                        CONF_ENABLE_INBOUND, DEFAULT_ENABLE_INBOUND
                    ),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_AUTO_REGISTER_WEBHOOK,
                    default=current.get(
                        CONF_AUTO_REGISTER_WEBHOOK, DEFAULT_AUTO_REGISTER_WEBHOOK
                    ),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_WEBHOOK_LOCAL_ONLY,
                    default=current.get(
                        CONF_WEBHOOK_LOCAL_ONLY, DEFAULT_WEBHOOK_LOCAL_ONLY
                    ),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_INCLUDE_FROM_ME,
                    default=current.get(
                        CONF_INCLUDE_FROM_ME, DEFAULT_INCLUDE_FROM_ME
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_ALLOWED_HANDLES,
                    default=current.get(CONF_ALLOWED_HANDLES, ""),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={"webhook_path": webhook_path},
        )
