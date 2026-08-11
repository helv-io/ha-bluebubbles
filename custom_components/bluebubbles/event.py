"""Event platform for BlueBubbles inbound messages."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_MESSAGE_RECEIVED, TRIGGER_TYPE_MESSAGE_RECEIVED

ENTITY_DESCRIPTION = EventEntityDescription(
    key="message",
    translation_key="message",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BlueBubbles event entity."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [BlueBubblesMessageEventEntity(entry, device_id=runtime.device_id)]
    )


class BlueBubblesMessageEventEntity(EventEntity):
    """Event entity that fires when an inbound BlueBubbles message arrives."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_description = ENTITY_DESCRIPTION

    def __init__(self, entry: ConfigEntry, *, device_id: str) -> None:
        """Initialize the event entity."""
        self._entry = entry
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_message"
        self._attr_event_types = [TRIGGER_TYPE_MESSAGE_RECEIVED]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to inbound message events."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_MESSAGE_RECEIVED, self._async_handle_bus_event
            )
        )

    @callback
    def _async_handle_bus_event(self, event) -> None:
        """Handle a bluebubbles_message_received bus event."""
        data: dict[str, Any] = dict(event.data)
        if data.get("device_id") != self._device_id:
            return

        attributes = {
            "text": data.get("text", ""),
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
        }
        self._trigger_event(TRIGGER_TYPE_MESSAGE_RECEIVED, attributes)
        self.async_write_ha_state()
