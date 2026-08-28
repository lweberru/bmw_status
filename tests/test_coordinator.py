"""Tests for the BMW Status coordinator projection boundary."""

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bmw_status.const import CARDATA_DOMAIN, CONF_CARDATA_DEVICE_ID, CONF_LICENSE_PLATE, DOMAIN
from custom_components.bmw_status.coordinator import BMWStatusCoordinator


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