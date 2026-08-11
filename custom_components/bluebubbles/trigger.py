"""Integration triggers for BlueBubbles inbound messages.

These purpose-specific triggers appear under Automations → Add trigger →
search "BlueBubbles" (modern Home Assistant trigger platform API).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol

from homeassistant.const import CONF_OPTIONS, CONF_TARGET
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.trigger import Trigger
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_MATCH_TYPE,
    CONF_PHRASE,
    EVENT_MESSAGE_RECEIVED,
    MATCH_TYPE_CONTAINS,
    MATCH_TYPES,
    TRIGGER_TYPE_MESSAGE_RECEIVED,
    TRIGGER_TYPE_PHRASE_RECEIVED,
)
from .matching import phrase_matches

if TYPE_CHECKING:
    from homeassistant.helpers.trigger import (
        TriggerActionRunner,
        TriggerConfig,
        TriggerNotTriggeredReporter,
    )

_MESSAGE_RECEIVED_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_TARGET): cv.TARGET_FIELDS,
        vol.Required(CONF_OPTIONS, default={}): {},
    }
)

_PHRASE_RECEIVED_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_TARGET): cv.TARGET_FIELDS,
        vol.Required(CONF_OPTIONS, default={}): {
            vol.Required(CONF_PHRASE): cv.string,
            vol.Optional(CONF_MATCH_TYPE, default=MATCH_TYPE_CONTAINS): vol.In(
                MATCH_TYPES
            ),
        },
    }
)


def _payload_from_event(data: dict[str, Any]) -> dict[str, Any]:
    """Map inbound event data onto automation trigger variables."""
    text = str(data.get("text") or "")
    return {
        "text": text,
        "message": text,
        "sender": data.get("sender", ""),
        "sender_name": data.get("sender_name", ""),
        "chat_guid": data.get("chat_guid", ""),
        "chat_identifier": data.get("chat_identifier", ""),
        "message_guid": data.get("message_guid", ""),
        "is_from_me": data.get("is_from_me", False),
        "timestamp": data.get("timestamp"),
        "attachments": data.get("attachments") or [],
        "service": data.get("service", ""),
        "subject": data.get("subject", ""),
        "device_id": data.get("device_id", ""),
        "entry_id": data.get("entry_id", ""),
    }


class BlueBubblesMessageTrigger(Trigger):
    """Base trigger that listens for ``bluebubbles_message_received``."""

    _schema: vol.Schema = _MESSAGE_RECEIVED_SCHEMA

    @classmethod
    async def async_validate_config(
        cls, hass: HomeAssistant, config: ConfigType
    ) -> ConfigType:
        """Validate trigger-specific config."""
        return cast(ConfigType, cls._schema(config))

    def __init__(self, hass: HomeAssistant, config: TriggerConfig) -> None:
        """Initialize trigger."""
        super().__init__(hass, config)
        self._key = config.key
        self._target = config.target
        self._options = config.options or {}

    @callback
    def _allowed_device_ids(self) -> set[str] | None:
        """Return targeted device ids, or None to accept every BlueBubbles device."""
        if not self._target:
            return None
        device_ids = self._target.get("device_id") or []
        return set(device_ids) if device_ids else None

    @callback
    def _event_matches(self, data: dict[str, Any]) -> bool:
        """Return whether this inbound message should fire the trigger."""
        return True

    @callback
    def _extra_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return trigger-specific extra payload fields."""
        return {}

    async def async_attach_runner(
        self,
        run_action: TriggerActionRunner,
        did_not_trigger: TriggerNotTriggeredReporter | None = None,
    ) -> CALLBACK_TYPE:
        """Attach the trigger to the inbound message bus event."""
        allowed = self._allowed_device_ids()

        @callback
        def _handle_event(event: Event) -> None:
            data = dict(event.data)
            device_id = data.get("device_id")
            if allowed is not None and device_id not in allowed:
                return
            if not self._event_matches(data):
                return

            payload = {**_payload_from_event(data), **self._extra_payload(data)}
            sender = payload.get("sender") or "unknown"
            run_action(
                payload,
                f"BlueBubbles message from {sender}",
                event.context,
            )

        return self._hass.bus.async_listen(EVENT_MESSAGE_RECEIVED, _handle_event)


class MessageReceivedTrigger(BlueBubblesMessageTrigger):
    """Fire for every inbound BlueBubbles message (after inbound filters)."""

    _schema = _MESSAGE_RECEIVED_SCHEMA


class PhraseReceivedTrigger(BlueBubblesMessageTrigger):
    """Fire when inbound message text matches a configured phrase."""

    _schema = _PHRASE_RECEIVED_SCHEMA

    @callback
    def _event_matches(self, data: dict[str, Any]) -> bool:
        text = str(data.get("text") or "")
        phrase = str(self._options.get(CONF_PHRASE) or "")
        match_type = self._options.get(CONF_MATCH_TYPE, MATCH_TYPE_CONTAINS)
        return phrase_matches(text, phrase, match_type)

    @callback
    def _extra_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "matched_phrase": str(self._options.get(CONF_PHRASE) or ""),
            "match_type": self._options.get(CONF_MATCH_TYPE, MATCH_TYPE_CONTAINS),
        }


TRIGGERS: dict[str, type[Trigger]] = {
    TRIGGER_TYPE_MESSAGE_RECEIVED: MessageReceivedTrigger,
    TRIGGER_TYPE_PHRASE_RECEIVED: PhraseReceivedTrigger,
}


async def async_get_triggers(hass: HomeAssistant) -> dict[str, type[Trigger]]:
    """Return triggers provided by BlueBubbles."""
    return TRIGGERS
