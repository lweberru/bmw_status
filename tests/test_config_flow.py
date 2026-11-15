"""Tests for the BMW Status CarData vehicle selection flow."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
import pytest
import voluptuous as vol
import voluptuous_serialize
from homeassistant.helpers import config_validation as cv
from unittest.mock import AsyncMock, patch
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bmw_status.const import CARDATA_DOMAIN, CONF_CARDATA_DEVICE_ID, DOMAIN
from custom_components.bmw_status.config_flow import BMWStatusConfigFlow, BMWStatusOptionsFlow, _fuel_schema


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


async def test_fuel_setup_and_options_preserve_and_clear_baselines(hass):
    flow = BMWStatusConfigFlow()
    flow.hass = hass
    result = await flow.async_step_card({"license_plate": "TEST"})
    assert result["step_id"] == "fuel"
    voluptuous_serialize.convert(result["data_schema"], custom_serializer=cv.custom_serializer)
    for invalid in (float("nan"), float("inf")):
        result = await flow.async_step_fuel({"initial_total_liters": invalid})
        assert result["errors"]["initial_total_liters"] == "fuel_invalid_number"
    result = await flow.async_step_fuel({"initial_since_refuel_liters": 10})
    assert result["errors"]["base"] == "fuel_initial_pair"
    result = await flow.async_step_fuel({"fuel_level_entity": "sensor.nonexistent"})
    assert result["errors"]["fuel_level_entity"] == "fuel_entity_not_found"
    result = await flow.async_step_fuel({"tank_capacity_liters": 50, "refuel_threshold_liters": 51})
    assert result["errors"]["refuel_threshold_liters"] == "fuel_threshold"
    values = {"tank_capacity_liters": 50, "initial_total_liters": 8000, "refuel_threshold_liters": 5}
    result = await flow.async_step_fuel(values)
    assert result["step_id"] == "image_provider"
    assert flow._options["fuel"] == values

    entry = MockConfigEntry(domain=DOMAIN, options={"fuel": values, "license_plate": "TEST"})
    options = BMWStatusOptionsFlow(entry)
    options.hass = hass
    assert (await options.async_step_init({}))["step_id"] == "fuel"
    assert options._options["fuel"] == values
    assert (await options.async_step_fuel({"refuel_threshold_liters": 5}))["step_id"] == "image_provider"
    assert "initial_total_liters" not in options._options["fuel"]
    assert options._options["license_plate"] == "TEST"


@pytest.mark.parametrize("values", [
    {"tank_capacity_liters": 0},
    {"initial_total_liters": -1},
    {"refuel_threshold_liters": 0},
])
def test_fuel_schema_rejects_invalid_numbers(values):
    with pytest.raises(vol.Invalid):
        _fuel_schema({})(values)


async def test_complete_setup_saves_fuel_options(hass):
    cardata_entry = MockConfigEntry(domain=CARDATA_DOMAIN)
    cardata_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=cardata_entry.entry_id, identifiers={(CARDATA_DOMAIN, "VIN-FUEL")}, name="BMW",
    )
    er.async_get(hass).async_get_or_create(
        domain="sensor", platform=CARDATA_DOMAIN, unique_id="fuel-flow", device_id=device.id,
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    flow_id = result["flow_id"]
    await hass.config_entries.flow.async_configure(flow_id, {CONF_CARDATA_DEVICE_ID: device.id})
    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["step_id"] == "fuel"
    await hass.config_entries.flow.async_configure(flow_id, {"tank_capacity_liters": 50, "initial_total_liters": 8000})
    await hass.config_entries.flow.async_configure(flow_id, {"enabled": False, "provider": "gemini", "view_mode": "auto", "scene_mode": "auto"})
    with patch("custom_components.bmw_status.async_setup_entry", new=AsyncMock(return_value=True)):
        result = await hass.config_entries.flow.async_configure(flow_id, {"enabled": False})
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["fuel"]["initial_total_liters"] == 8000