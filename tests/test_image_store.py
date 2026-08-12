"""Tests for BMW Status image cache storage."""

from custom_components.bmw_status.image_store import ImageStore


async def test_image_store_round_trips_and_clears_one_vehicle_directory(hass):
    """The store sanitizes its path and atomically retains only its own cache."""
    store = ImageStore(hass, "VIN/123")

    assert await store.async_load(hass) == {"version": 1, "images": {}}
    url = await store.async_write_png(hass, "hero.png", b"png-bytes")
    await store.async_save(hass, {"version": 1, "images": {"state": {"hero": "hero.png"}}})

    assert url == "/local/bmw_status/VIN123/hero.png"
    assert await store.async_exists(hass, "hero.png")
    assert await store.async_load(hass) == {"version": 1, "images": {"state": {"hero": "hero.png"}}}

    await store.async_clear(hass)

    assert not await store.async_exists(hass, "hero.png")
    assert await store.async_load(hass) == {"version": 1, "images": {}}