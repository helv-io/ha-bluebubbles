"""Device triggers for BlueBubbles inbound messages."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, Context, HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_MATCH_TYPE,
    CONF_PHRASE,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
    MATCH_TYPE_CONTAINS,
    MATCH_TYPES,
    TRIGGER_TYPE_MESSAGE_RECEIVED,
    TRIGGER_TYPE_PHRASE_RECEIVED,
)
from .matching import phrase_matches

TRIGGER_TYPES = {TRIGGER_TYPE_MESSAGE_RECEIVED, TRIGGER_TYPE_PHRASE_RECEIVED}

# Module-level constant required by device automation discovery.
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


async def async_validate_trigger_config(
    hass: HomeAssistant, config: ConfigType
) -> ConfigType:
    """Validate a device trigger config."""
    return TRIGGER_SCHEMA(config)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """Return device triggers for BlueBubbles devices.

    Triggers are always listed when the BlueBubbles device exists. They simply
    will not fire until inbound messaging is enabled under Configure.
    """
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


def _enrich_trigger_payload(
    *,
    trigger: dict[str, Any],
    trigger_type: str,
    device_id: str,
    event_data: dict[str, Any],
    phrase: str,
    match_type: str,
) -> dict[str, Any]:
    """Build the flattened device-trigger payload used by templates."""
    text = str(event_data.get("text") or "")
    payload: dict[str, Any] = {
        **trigger,
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
    }
    if trigger_type == TRIGGER_TYPE_PHRASE_RECEIVED:
        payload["matched_phrase"] = phrase
        payload["match_type"] = match_type
    return payload


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a device trigger via the core event trigger helper."""
    config = TRIGGER_SCHEMA(config)
    trigger_type = config[CONF_TYPE]
    device_id = config[CONF_DEVICE_ID]
    phrase = str(config.get(CONF_PHRASE) or "")
    match_type = config.get(CONF_MATCH_TYPE, MATCH_TYPE_CONTAINS)

    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: EVENT_MESSAGE_RECEIVED,
            event_trigger.CONF_EVENT_DATA: {CONF_DEVICE_ID: device_id},
        }
    )

    async def _wrapped_action(
        run_variables: dict[str, Any], context: Context | None = None
    ) -> Any:
        """Filter phrase matches and flatten event fields onto trigger."""
        trigger = dict(run_variables.get("trigger") or {})
        event = trigger.get("event")
        event_data: dict[str, Any] = dict(event.data) if event is not None else {}
        text = str(event_data.get("text") or "")

        if trigger_type == TRIGGER_TYPE_PHRASE_RECEIVED:
            if not phrase_matches(text, phrase, match_type):
                return None

        enriched = _enrich_trigger_payload(
            trigger=trigger,
            trigger_type=trigger_type,
            device_id=device_id,
            event_data=event_data,
            phrase=phrase,
            match_type=match_type,
        )
        result = action({"trigger": enriched}, context)
        if asyncio.iscoroutine(result):
            return await result
        return result

    return await event_trigger.async_attach_trigger(
        hass,
        event_config,
        _wrapped_action,
        trigger_info,
        platform_type="device",
    )


# Backwards-compatible alias for unit tests that imported the private helper.
_phrase_matches = phrase_matches
