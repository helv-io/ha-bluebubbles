"""Shared phrase-matching helpers for BlueBubbles triggers."""

from __future__ import annotations

import logging
import re

from .const import MATCH_TYPE_EXACT, MATCH_TYPE_REGEX

_LOGGER = logging.getLogger(__name__)


def phrase_matches(text: str, phrase: str, match_type: str) -> bool:
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
