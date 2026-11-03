"""Tests for the BMW Status coordinator projection boundary."""

from copy import deepcopy
from unittest.mock import AsyncMock, Mock

import pytest

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bmw_status.const import CARDATA_DOMAIN, CONF_CARDATA_DEVICE_ID, CONF_LICENSE_PLATE, DOMAIN
from custom_components.bmw_status.coordinator import BMWStatusCoordinator, _weather_description
from custom_components.bmw_status.image_jobs import ImageJobState


@pytest.fixture
def image_coordinator(hass, monkeypatch):
    """Configure image generation without invoking remote services."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CARDATA_DEVICE_ID: "vehicle-device"},
        options={"image": {"enabled": True, "provider": "openai", "api_key": "test-key"}},
    )
    entry.add_to_hass(hass)
    coordinator = BMWStatusCoordinator(hass, entry)
    monkeypatch.setattr(coordinator, "_async_build_image_context", AsyncMock(return_value={}))
    monkeypatch.setattr(coordinator._image_jobs, "async_request", Mock())
    return coordinator


async def test_image_key_ignores_metrics_and_published_image_urls(image_coordinator):
    """Routine telemetry and image publication must not incur another generation."""
    first = {"vehicle": {"name": "BMW"}, "status": {"key": "parked"}, "entities": {"fuel": {"state": "50"}}}
    changed = deepcopy(first)
    changed["entities"]["fuel"]["state"] = "49"
    changed["images"] = ["/local/bmw_status/old.png"]
    changed["tire_image"] = "/local/bmw_status/tire.png"
    assert image_coordinator._state_image_key(first) == image_coordinator._state_image_key(changed)

    changed["status"]["key"] = "driving"
    assert image_coordinator._state_image_key(first) != image_coordinator._state_image_key(changed)


@pytest.mark.parametrize("failed", [False, True])
async def test_previous_image_remains_visible_while_new_state_is_pending_or_failed(image_coordinator, failed):
    """Reuse an existing state image, including legacy cache entries after reload."""
    coordinator = image_coordinator
    filename = "last-state.png"
    url = await coordinator._image_store.async_write_png(coordinator.hass, filename, b"png")
    coordinator._image_index["images"] = {
        "state-legacy": {"filename": filename, "local_url": url, "updated_at": "2026-11-01"},
        "state-deleted": {"filename": "missing.png", "local_url": "/missing.png", "updated_at": "2026-11-02"},
        "tire-reference": {"filename": filename, "local_url": "/wrong-tire.png", "updated_at": "2026-11-03"},
    }
    if failed:
        coordinator._image_state = ImageJobState("error", "Provider unavailable")
    data = await coordinator._async_update_data()

    assert data["presentation"]["images"] == [url]
    assert coordinator._image_jobs.async_request.call_count == 2
    if failed:
        assert data["image_status"] == "error"
        assert data["error"] == "Provider unavailable"


async def test_render_uses_latest_snapshot_key_and_reuses_result(image_coordinator, monkeypatch):
    """A queued request must not cache a new scene under an obsolete state key."""
    coordinator = image_coordinator
    coordinator.async_set_updated_data({"presentation": {"vehicle": {"name": "BMW"}, "status": {"key": "driving"}}})
    generate = AsyncMock(return_value=b"png")
    monkeypatch.setattr("custom_components.bmw_status.coordinator.async_generate_state_render", generate)
    monkeypatch.setattr(coordinator, "async_request_refresh", AsyncMock())
    expected_key = coordinator._state_image_key(coordinator.data["presentation"])

    await coordinator._async_render_image("state-obsolete")
    assert "state-obsolete" not in coordinator._image_index["images"]
    assert expected_key in coordinator._image_index["images"]
    assert "driving on a road" in generate.call_args.args[2]

    await coordinator._async_render_image("state-obsolete")
    generate.assert_awaited_once()


async def test_regeneration_uses_same_key_as_update_with_published_images(image_coordinator):
    """Adding image URLs to the projection must not change the regeneration key."""
    coordinator = image_coordinator
    data = await coordinator._async_update_data()
    expected_key = coordinator._image_jobs.async_request.call_args_list[0].args[0]
    data["presentation"]["images"] = ["/local/previous.png"]
    coordinator.async_set_updated_data(data)
    coordinator._image_index["images"][expected_key] = {"filename": "previous.png"}
    coordinator._image_jobs.async_request.reset_mock()

    await coordinator.async_regenerate_images()

    assert expected_key not in coordinator._image_index["images"]
    coordinator._image_jobs.async_request.assert_any_call(expected_key, force=True)


async def test_coordinator_projects_only_the_selected_cardata_device(hass):
    """A BMW Status entry must never mix sensor data from a second CarData vehicle."""
    cardata_entry = MockConfigEntry(domain=CARDATA_DOMAIN, entry_id="cardata-entry")
    cardata_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    selected_device = device_registry.async_get_or_create(
        config_entry_id=cardata_entry.entry_id,
        identifiers={(CARDATA_DOMAIN, "VIN-ONE")},
        name="BMW One",
    )
    other_device = device_registry.async_get_or_create(
        config_entry_id=cardata_entry.entry_id,
        identifiers={(CARDATA_DOMAIN, "VIN-TWO")},
        name="BMW Two",
    )
    selected_entity = entity_registry.async_get_or_create(
        domain="sensor",
        platform=CARDATA_DOMAIN,
        unique_id="vin_one_soc",
        device_id=selected_device.id,
    )
    other_entity = entity_registry.async_get_or_create(
        domain="sensor",
        platform=CARDATA_DOMAIN,
        unique_id="vin_two_fuel",
        device_id=other_device.id,
    )
    hass.states.async_set(selected_entity.entity_id, "81", {"friendly_name": "State of Charge", "unit_of_measurement": "%"})
    hass.states.async_set(other_entity.entity_id, "9", {"friendly_name": "Remaining Fuel", "unit_of_measurement": "L"})
    status_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CARDATA_DEVICE_ID: selected_device.id},
        options={},
    )
    status_entry.add_to_hass(hass)
    coordinator = BMWStatusCoordinator(hass, status_entry)

    data = await coordinator._async_update_data()

    assert data["schema_version"] == 1
    assert data["presentation"]["vehicle"]["name"] == "BMW One"
    assert data["presentation"]["entities"]["battery_charge"]["entity_id"] == selected_entity.entity_id
    assert data["presentation"]["entities"]["fuel"] is None
    assert "map" not in data["presentation"]
    assert data["image_status"] == "disabled"


async def test_image_prompt_uses_cardata_vehicle_identity_and_configured_plate(hass):
    """Server-side image prompts retain the detailed vehicle identity from CarData."""
    cardata_entry = MockConfigEntry(domain=CARDATA_DOMAIN, entry_id="cardata-entry")
    cardata_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=cardata_entry.entry_id,
        identifiers={(CARDATA_DOMAIN, "VIN-IDENTITY")},
        name="My BMW",
        manufacturer="BMW",
        model="X5",
    )
    entity = er.async_get(hass).async_get_or_create(
        domain="sensor", platform=CARDATA_DOMAIN, unique_id="vin_identity_basic", device_id=device.id
    )
    hass.states.async_set(
        entity.entity_id,
        "ok",
        {
            "friendly_name": "Vehicle Basic Data",
            "vehicle_basic_data_raw": {
                "brand": "BMW",
                "modelName": "X5 xDrive50e",
                "series": "G05",
                "constructionDate": "2024-03-01",
                "colourDescription": "Tanzanite Blue",
                "bodyType": "SAV",
            },
        },
    )
    status_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CARDATA_DEVICE_ID: device.id},
        options={CONF_LICENSE_PLATE: "M-AB 1234"},
    )
    status_entry.add_to_hass(hass)
    coordinator = BMWStatusCoordinator(hass, status_entry)

    prompt = coordinator._build_state_render_prompt({"vehicle": coordinator._vehicle_metadata(device.id), "status": {"key": "parked"}})

    assert "2024 Tanzanite Blue BMW X5 G05 SAV" in prompt
    assert "License plate text must remain exactly: M-AB 1234." in prompt


async def test_image_prompt_keeps_open_driver_door_attached(hass):
    """The image prompt must distinguish the driver's door from the passenger door."""
    status_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CARDATA_DEVICE_ID: "device-id"},
        options={},
    )
    status_entry.add_to_hass(hass)
    coordinator = BMWStatusCoordinator(hass, status_entry)

    prompt = coordinator._build_state_render_prompt(
        {
            "vehicle": {"name": "BMW"},
            "status": {"key": "parked"},
            "groups": {
                "doors": [{
                    "name": "Door state (front driver)",
                    "entity_id": "binary_sensor.front_driver_door",
                    "state": "on",
                }],
            },
        }
    )

    assert "front driver's door on the visible side" in prompt
    assert "still attached to its hinges" in prompt
    assert "do not remove it" in prompt
    assert "front passenger door closed" in prompt


async def test_image_prompt_uses_weather_category_without_measurements_or_location(hass):
    """The scene retains season and weather without highly variable details."""
    status_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CARDATA_DEVICE_ID: "device-id"},
        options={},
    )
    status_entry.add_to_hass(hass)
    coordinator = BMWStatusCoordinator(hass, status_entry)

    prompt = coordinator._build_state_render_prompt(
        {
            "vehicle": {"name": "BMW"},
            "status": {"key": "parked"},
            "image_context": {
                "location": "Heilbronn, Germany",
                "season": "summer",
                "time_of_day": "afternoon",
                "weather": "clear sky",
                "temperature": 24,
                "precipitation": 0.7,
            },
        }
    )

    assert "Heilbronn, Germany" not in prompt
    assert "summer" in prompt
    assert "clear sky" in prompt
    assert "24" not in prompt
    assert "0.7" not in prompt
    assert "afternoon" in prompt


@pytest.mark.parametrize("change", [
    {"temperature": -5.2},
    {"precipitation": 15.6},
    {"location": "Berlin, Germany"},
    {"temperature": 17, "precipitation": 0.1, "location": "Hamburg, Germany"},
])
async def test_image_cache_ignores_temperature_precipitation_and_location(image_coordinator, change):
    """Different measurements or addresses must reuse the same parked image."""
    first = {
        "vehicle": {"name": "BMW"},
        "status": {"key": "parked"},
        "image_context": {
            "weather": "rainy", "temperature": 12.1, "precipitation": 0.5,
            "location": "Heilbronn, Germany", "season": "autumn", "time_of_day": "afternoon",
        },
    }
    changed = deepcopy(first)
    changed["image_context"].update(change)

    assert image_coordinator._build_state_render_prompt(first) == image_coordinator._build_state_render_prompt(changed)
    assert image_coordinator._state_image_key(first) == image_coordinator._state_image_key(changed)


@pytest.mark.parametrize("weather_codes, same_image", [
    ((61, 65), True),  # Light and heavy rain share a category.
    ((71, 75), True),  # Light and heavy snowfall share a category.
    ((0, 61), False),  # Sun to rain changes the scene.
    ((61, 71), False),  # Rain to snow changes the scene.
    ((3, 45), False),  # Overcast to fog changes the scene.
])
async def test_image_cache_responds_to_weather_categories(image_coordinator, weather_codes, same_image):
    """Only category changes, rather than precipitation intensity, invalidate images."""
    first = {"vehicle": {"name": "BMW"}, "status": {"key": "parked"},
             "image_context": {"weather": _weather_description(weather_codes[0])}}
    changed = deepcopy(first)
    changed["image_context"]["weather"] = _weather_description(weather_codes[1])

    assert (image_coordinator._state_image_key(first) == image_coordinator._state_image_key(changed)) is same_image
