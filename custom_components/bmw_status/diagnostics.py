"""Diagnostics support for BMW Status."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_CARDATA_DEVICE_ID, CONF_IMAGE, CONF_IMAGE_API_KEY


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return the non-sensitive Phase-1 configuration for troubleshooting."""
    options = dict(entry.options)
    image = options.get(CONF_IMAGE)
    if isinstance(image, dict):
        options[CONF_IMAGE] = {key: value for key, value in image.items() if key != CONF_IMAGE_API_KEY}
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "cardata_device_id": entry.data.get(CONF_CARDATA_DEVICE_ID),
        "options": options,
    }