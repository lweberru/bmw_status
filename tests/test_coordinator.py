"""Tests for the BMW Status coordinator projection boundary."""

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bmw_status.const import CARDATA_DOMAIN, CONF_CARDATA_DEVICE_ID, DOMAIN
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