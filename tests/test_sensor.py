"""Tests for the public BMW Status sensor contract."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bmw_status.const import CONF_CARDATA_DEVICE_ID, DOMAIN
from custom_components.bmw_status.coordinator import BMWStatusCoordinator
from custom_components.bmw_status.sensor import BMWStatusSensor


async def test_status_sensor_exposes_versioned_presentation_contract(hass):
    """The card receives the coordinator payload without backend-only fields."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CARDATA_DEVICE_ID: "vehicle-device"})
    coordinator = BMWStatusCoordinator(hass, entry)
    payload = {
        "schema_version": 1,
        "presentation": {"status": {"key": "parked"}, "vehicle": {"name": "Test BMW"}},
        "image_status": "ready",
        "updated_at": "2026-08-11T12:00:00+00:00",
        "error": None,
        "retry_after": None,
    }
    coordinator.async_set_updated_data(payload)
    sensor = BMWStatusSensor(entry, coordinator)

    assert sensor.native_value == "parked"
    assert sensor.extra_state_attributes == payload
    assert "map" not in sensor.extra_state_attributes["presentation"]