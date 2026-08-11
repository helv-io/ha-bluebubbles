"""Device triggers for BlueBubbles inbound messages."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_MATCH_TYPE,
    CONF_PHRASE,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
    MATCH_TYPE_CONTAINS,
    MATCH_TYPE_EXACT,
    MATCH_TYPE_REGEX,
    MATCH_TYPES,
    TRIGGER_TYPE_MESSAGE_RECEIVED,
    TRIGGER_TYPE_PHRASE_RECEIVED,
)

_LOGGER = logging.getLogger(__name__)

TRIGGER_TYPES = {TRIGGER_TYPE_MESSAGE_RECEIVED, TRIGGER_TYPE_PHRASE_RECEIVED}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
        vol.Optional(CONF_PHRASE): cv.string,
        vol.Optional(CONF_MATCH_TYPE, default=MATCH_TYPE_CONTAINS): vol.In(MATCH_TYPES),
    }
)


def _is_bluebubbles_device(device: dr.DeviceEntry) -> bool:
    """Return True if the device belongs to this integration."""
    return any(identifier[0] == DOMAIN for identifier in device.identifiers)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """Return device triggers for BlueBubbles devices."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    if device is None or not _is_bluebubbles_device(device):
        return []

    return [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: TRIGGER_TYPE_MESSAGE_RECEIVED,
        },
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: TRIGGER_TYPE_PHRASE_RECEIVED,
        },
    ]


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """Return extra fields for phrase matching in the automation UI."""
    if config[CONF_TYPE] != TRIGGER_TYPE_PHRASE_RECEIVED:
        return {}

    return {
        "extra_fields": vol.Schema(
            {
                vol.Required(CONF_PHRASE): cv.string,
                vol.Optional(
                    CONF_MATCH_TYPE, default=MATCH_TYPE_CONTAINS
                ): vol.In(sorted(MATCH_TYPES)),
            }
        )
    }


def _phrase_matches(text: str, phrase: str, match_type: str) -> bool:
    """Return True if text matches phrase using the selected strategy."""
    if not phrase:
        return False

    if match_type == MATCH_TYPE_EXACT:
        return text.strip().lower() == phrase.strip().lower()

    if match_type == MATCH_TYPE_REGEX:
        try:
            return re.search(phrase, text, re.IGNORECASE) is not None
        except re.error:
            _LOGGER.warning("Invalid regex in BlueBubbles phrase trigger: %s", phrase)
            return False

    # Default: case-insensitive contains
    return phrase.lower() in text.lower()


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a device trigger to the inbound message event."""
    trigger_type = config[CONF_TYPE]
    device_id = config[CONF_DEVICE_ID]
    phrase = str(config.get(CONF_PHRASE) or "")
    match_type = config.get(CONF_MATCH_TYPE, MATCH_TYPE_CONTAINS)
    job = HassJob(action, f"BlueBubbles device trigger {trigger_type}")

    @callback
    def _handle_event(event) -> None:
        """Filter inbound events and run the automation action."""
        event_data: dict[str, Any] = event.data
        if event_data.get("device_id") != device_id:
            return

        text = str(event_data.get("text") or "")
        if trigger_type == TRIGGER_TYPE_PHRASE_RECEIVED:
            if not _phrase_matches(text, phrase, match_type):
                return

        trigger_payload: dict[str, Any] = {
            **trigger_info["trigger_data"],
            "platform": "device",
            "domain": DOMAIN,
            "type": trigger_type,
            "device_id": device_id,
            "text": text,
            "message": text,
            "sender": event_data.get("sender", ""),
            "sender_name": event_data.get("sender_name", ""),
            "chat_guid": event_data.get("chat_guid", ""),
            "chat_identifier": event_data.get("chat_identifier", ""),
            "message_guid": event_data.get("message_guid", ""),
            "is_from_me": event_data.get("is_from_me", False),
            "timestamp": event_data.get("timestamp"),
            "attachments": event_data.get("attachments") or [],
            "service": event_data.get("service", ""),
            "subject": event_data.get("subject", ""),
            "event": event,
        }
        if trigger_type == TRIGGER_TYPE_PHRASE_RECEIVED:
            trigger_payload["matched_phrase"] = phrase
            trigger_payload["match_type"] = match_type

        hass.async_run_hass_job(job, {"trigger": trigger_payload})

    return hass.bus.async_listen(EVENT_MESSAGE_RECEIVED, _handle_event)
