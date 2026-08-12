"""Tests for BMW Status service dispatch."""

from unittest.mock import AsyncMock

from custom_components.bmw_status.const import (
    DATA_COORDINATOR,
    DOMAIN,
    SERVICE_CLEAR_IMAGE_CACHE,
    SERVICE_REFRESH,
    SERVICE_REGENERATE_IMAGES,
)
from custom_components.bmw_status.services import async_register_services


async def test_services_target_all_or_one_config_entry(hass):
    """Services fan out by default and honor an explicit entry ID."""
    first = AsyncMock()
    second = AsyncMock()
    hass.data[DOMAIN] = {
        "entry-one": {DATA_COORDINATOR: first},
        "entry-two": {DATA_COORDINATOR: second},
    }
    await async_register_services(hass)

    await hass.services.async_call(DOMAIN, SERVICE_REFRESH, blocking=True)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_REGENERATE_IMAGES,
        {"entry_id": "entry-one"},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAR_IMAGE_CACHE,
        {"entry_id": "entry-two"},
        blocking=True,
    )

    first.async_request_refresh.assert_awaited_once()
    second.async_request_refresh.assert_awaited_once()
    first.async_regenerate_images.assert_awaited_once()
    second.async_regenerate_images.assert_not_awaited()
    first.async_clear_image_cache.assert_not_awaited()
    second.async_clear_image_cache.assert_awaited_once()