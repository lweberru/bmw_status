"""Explicit BMW Status backend actions."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    SERVICE_CLEAR_IMAGE_CACHE,
    SERVICE_REFRESH,
    SERVICE_REGENERATE_IMAGES,
)

SERVICE_SCHEMA = vol.Schema({vol.Optional("entry_id"): cv.string})


async def async_register_services(hass: HomeAssistant) -> None:
    """Register services shared by all BMW Status entries."""
    async def handle_refresh(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            await coordinator.async_request_refresh()

    async def handle_regenerate(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            await coordinator.async_regenerate_images()

    async def handle_clear_cache(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            await coordinator.async_clear_image_cache()

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh, schema=SERVICE_SCHEMA)
    if not hass.services.has_service(DOMAIN, SERVICE_REGENERATE_IMAGES):
        hass.services.async_register(DOMAIN, SERVICE_REGENERATE_IMAGES, handle_regenerate, schema=SERVICE_SCHEMA)
    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_IMAGE_CACHE):
        hass.services.async_register(DOMAIN, SERVICE_CLEAR_IMAGE_CACHE, handle_clear_cache, schema=SERVICE_SCHEMA)


def _coordinators(hass: HomeAssistant, call: ServiceCall):
    """Yield all or one selected coordinator."""
    requested_entry_id = call.data.get("entry_id")
    for entry_id, data in hass.data.get(DOMAIN, {}).items():
        if requested_entry_id and entry_id != requested_entry_id:
            continue
        yield data[DATA_COORDINATOR]