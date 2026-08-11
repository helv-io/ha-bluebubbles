"""Constants for the BlueBubbles integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "bluebubbles"

CONF_HOST: Final = "host"
CONF_PASSWORD: Final = "password"
CONF_SSL: Final = "ssl"

# Options (additive / backward compatible)
CONF_ENABLE_INBOUND: Final = "enable_inbound"
CONF_WEBHOOK_ID: Final = "webhook_id"
CONF_AUTO_REGISTER_WEBHOOK: Final = "auto_register_webhook"
CONF_WEBHOOK_LOCAL_ONLY: Final = "webhook_local_only"
CONF_INCLUDE_FROM_ME: Final = "include_from_me"
CONF_ALLOWED_HANDLES: Final = "allowed_handles"
CONF_BB_WEBHOOK_ID: Final = "bb_webhook_id"

DEFAULT_ENABLE_INBOUND: Final = False
DEFAULT_AUTO_REGISTER_WEBHOOK: Final = True
DEFAULT_WEBHOOK_LOCAL_ONLY: Final = True
DEFAULT_INCLUDE_FROM_ME: Final = False

# Event fired for inbound messages (device triggers subscribe to this)
EVENT_MESSAGE_RECEIVED: Final = f"{DOMAIN}_message_received"

# Device trigger types
TRIGGER_TYPE_MESSAGE_RECEIVED: Final = "message_received"
TRIGGER_TYPE_PHRASE_RECEIVED: Final = "phrase_received"

CONF_PHRASE: Final = "phrase"
CONF_MATCH_TYPE: Final = "match_type"

MATCH_TYPE_CONTAINS: Final = "contains"
MATCH_TYPE_EXACT: Final = "exact"
MATCH_TYPE_REGEX: Final = "regex"
MATCH_TYPES: Final = {
    MATCH_TYPE_CONTAINS,
    MATCH_TYPE_EXACT,
    MATCH_TYPE_REGEX,
}

# BlueBubbles webhook event types we care about
BB_EVENT_NEW_MESSAGE: Final = "new-message"
