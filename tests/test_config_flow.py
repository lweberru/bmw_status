"""Tests for the BMW Status CarData vehicle selection flow."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bmw_status.const import CARDATA_DOMAIN, CONF_CARDATA_DEVICE_ID, DOMAIN


async def test_config_flow_selects_only_cardata_vehicle_devices(hass):
    """Only CarData devices with registered entities are offered to the user."""
    cardata_entry = MockConfigEntry(domain=CARDATA_DOMAIN, entry_id="cardata-entry")
    cardata_entry.add_to_hass(hass)
    other_entry = MockConfigEntry(domain="other", entry_id="other-entry")
    other_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    cardata_device = device_registry.async_get_or_create(
        config_entry_id="cardata-entry",
        identifiers={(CARDATA_DOMAIN, "TESTVIN")},
        name="Test BMW",
    )
    other_device = device_registry.async_get_or_create(
        config_entry_id="other-entry",
        identifiers={("other", "other-device")},
        name="Other device",
    )
    entity_registry.async_get_or_create(
        domain="sensor",
        platform=CARDATA_DOMAIN,
        unique_id="testvin_soc",
        device_id=cardata_device.id,
    )
    entity_registry.async_get_or_create(
        domain="sensor",
        platform="other",
        unique_id="other_value",
        device_id=other_device.id,
    )

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    schema = result["data_schema"].schema
    selector = next(value for key, value in schema.items() if key.schema == CONF_CARDATA_DEVICE_ID)
    assert selector.container == {cardata_device.id: "Test BMW"}


async def test_config_flow_aborts_without_cardata_vehicle(hass):
    """The flow cannot create a BMW Status entry before CarData provides a vehicle."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_cardata_vehicles"