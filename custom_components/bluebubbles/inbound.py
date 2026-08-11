"""Inbound message listener via Home Assistant webhooks + BlueBubbles."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp.web import Request, Response

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.network import get_url

from .api import BlueBubblesApi, normalize_inbound_message
from .const import (
    BB_EVENT_NEW_MESSAGE,
    CONF_ALLOWED_HANDLES,
    CONF_AUTO_REGISTER_WEBHOOK,
    CONF_BB_WEBHOOK_ID,
    CONF_ENABLE_INBOUND,
    CONF_INCLUDE_FROM_ME,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_LOCAL_ONLY,
    DEFAULT_AUTO_REGISTER_WEBHOOK,
    DEFAULT_INCLUDE_FROM_ME,
    DEFAULT_WEBHOOK_LOCAL_ONLY,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
)

_LOGGER = logging.getLogger(__name__)


def _parse_allowed_handles(raw: str | None) -> set[str]:
    """Parse a comma/semicolon separated allow-list into lowercase handles."""
    if not raw:
        return set()
    parts = [
        part.strip().lower()
        for part in raw.replace(";", ",").split(",")
        if part.strip()
    ]
    return set(parts)


class InboundManager:
    """Manage HA webhook registration and optional BlueBubbles auto-subscribe."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: BlueBubblesApi,
        *,
        device_id: str,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.api = api
        self.device_id = device_id
        self._webhook_id: str | None = None
        self._bb_webhook_id: str | int | None = entry.options.get(CONF_BB_WEBHOOK_ID)
        self._registered = False

    @property
    def options(self) -> dict[str, Any]:
        """Merged options for inbound behavior."""
        return dict(self.entry.options)

    def webhook_path(self) -> str | None:
        """Return the relative webhook path if configured."""
        webhook_id = self._webhook_id or self.options.get(CONF_WEBHOOK_ID)
        if not webhook_id:
            return None
        return webhook.async_generate_path(webhook_id)

    def webhook_url(self) -> str | None:
        """Best-effort absolute webhook URL for documentation / auto-register."""
        webhook_id = self._webhook_id or self.options.get(CONF_WEBHOOK_ID)
        if not webhook_id:
            return None
        try:
            return webhook.async_generate_url(self.hass, webhook_id)
        except Exception:  # noqa: BLE001 - network URL may be unavailable at setup
            try:
                base = get_url(
                    self.hass,
                    prefer_external=True,
                    allow_cloud=True,
                )
            except Exception:  # noqa: BLE001
                return self.webhook_path()
            return f"{base}{webhook.async_generate_path(webhook_id)}"

    async def async_start(self) -> None:
        """Register the HA webhook when inbound messaging is enabled."""
        if not self.options.get(CONF_ENABLE_INBOUND, False):
            _LOGGER.debug(
                "Inbound messaging disabled for entry %s", self.entry.entry_id
            )
            return

        webhook_id = self.options.get(CONF_WEBHOOK_ID)
        if not webhook_id:
            # Options flow normally creates this; generate as a safety net without
            # persisting here (persisting would reload the entry mid-setup).
            webhook_id = webhook.async_generate_id()
            _LOGGER.warning(
                "Inbound enabled without webhook_id; using ephemeral id until "
                "options are saved again"
            )

        self._webhook_id = webhook_id
        local_only = bool(
            self.options.get(CONF_WEBHOOK_LOCAL_ONLY, DEFAULT_WEBHOOK_LOCAL_ONLY)
        )

        webhook.async_register(
            self.hass,
            DOMAIN,
            "BlueBubbles",
            webhook_id,
            self._handle_webhook,
            local_only=local_only,
        )
        self._registered = True
        _LOGGER.info(
            "Registered BlueBubbles inbound webhook (%s)",
            webhook.async_generate_path(webhook_id),
        )

        if self.options.get(CONF_AUTO_REGISTER_WEBHOOK, DEFAULT_AUTO_REGISTER_WEBHOOK):
            await self._async_register_with_bluebubbles()

    async def async_stop(self) -> None:
        """Unregister HA webhook and best-effort remove BB server registration."""
        webhook_id = self._webhook_id or self.options.get(CONF_WEBHOOK_ID)
        if self._registered and webhook_id:
            webhook.async_unregister(self.hass, webhook_id)
            self._registered = False
            _LOGGER.debug("Unregistered BlueBubbles inbound webhook %s", webhook_id)

        bb_webhook_id = self._bb_webhook_id
        if bb_webhook_id is not None:
            try:
                await self.api.async_delete_webhook(bb_webhook_id)
                _LOGGER.debug(
                    "Deleted BlueBubbles server webhook id %s", bb_webhook_id
                )
            except HomeAssistantError as err:
                _LOGGER.warning(
                    "Failed to delete BlueBubbles server webhook %s: %s",
                    bb_webhook_id,
                    err,
                )
            self._bb_webhook_id = None

        self._webhook_id = None

    async def _async_register_with_bluebubbles(self) -> None:
        """Create (or replace) a new-message webhook on the BlueBubbles server."""
        url = self.webhook_url()
        if not url or url.startswith("/"):
            _LOGGER.warning(
                "Cannot auto-register BlueBubbles webhook: Home Assistant URL "
                "is unavailable. Register manually in BlueBubbles using path %s",
                self.webhook_path(),
            )
            return

        # Remove a previous registration for this HA webhook URL if present.
        try:
            existing = await self.api.async_list_webhooks()
        except HomeAssistantError as err:
            _LOGGER.warning("Could not list BlueBubbles webhooks: %s", err)
            existing = []

        for item in existing:
            if item.get("url") == url and item.get("id") is not None:
                try:
                    await self.api.async_delete_webhook(item["id"])
                except HomeAssistantError as err:
                    _LOGGER.debug(
                        "Failed removing stale BlueBubbles webhook %s: %s",
                        item.get("id"),
                        err,
                    )

        try:
            result = await self.api.async_create_webhook(url, [BB_EVENT_NEW_MESSAGE])
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Auto-register with BlueBubbles failed (%s). You can add the "
                "webhook manually in BlueBubbles Server → API & Webhooks: %s",
                err,
                url,
            )
            return

        bb_id = (result.get("data") or {}).get("id")
        if bb_id is not None:
            self._bb_webhook_id = bb_id
            _LOGGER.info(
                "Auto-registered BlueBubbles webhook id %s → %s", bb_id, url
            )

    async def _handle_webhook(
        self, hass: HomeAssistant, webhook_id: str, request: Request
    ) -> Response:
        """Handle an inbound BlueBubbles webhook POST."""
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001 - malformed webhook body
            _LOGGER.warning("BlueBubbles webhook received non-JSON body")
            return Response(status=200, text="ok")

        if not isinstance(payload, dict):
            return Response(status=200, text="ok")

        await self.async_handle_payload(payload)
        return Response(status=200, text="ok")

    async def async_handle_payload(self, payload: dict[str, Any]) -> None:
        """Process a BlueBubbles webhook payload (also used by tests)."""
        normalized = normalize_inbound_message(payload)
        if normalized is None:
            _LOGGER.debug(
                "Ignoring BlueBubbles webhook payload type=%s", payload.get("type")
            )
            return

        include_from_me = bool(
            self.options.get(CONF_INCLUDE_FROM_ME, DEFAULT_INCLUDE_FROM_ME)
        )
        if normalized["is_from_me"] and not include_from_me:
            _LOGGER.debug("Ignoring outbound/from-me BlueBubbles message")
            return

        allowed = _parse_allowed_handles(self.options.get(CONF_ALLOWED_HANDLES))
        if allowed:
            sender = str(normalized.get("sender") or "").lower()
            chat_identifier = str(normalized.get("chat_identifier") or "").lower()
            if sender not in allowed and chat_identifier not in allowed:
                _LOGGER.debug(
                    "Ignoring message from %s (not in allowed_handles)",
                    normalized.get("sender"),
                )
                return

        event_data = {
            **normalized,
            "device_id": self.device_id,
            "entry_id": self.entry.entry_id,
        }
        self._fire_message_event(event_data)

    @callback
    def _fire_message_event(self, event_data: dict[str, Any]) -> None:
        """Fire the Home Assistant event used by device triggers."""
        _LOGGER.debug(
            "Inbound BlueBubbles message from %s: %s",
            event_data.get("sender"),
            (event_data.get("text") or "")[:80],
        )
        self.hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, event_data)
