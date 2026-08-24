"""Mutable vehicle entities for exercising BMW Status locally."""

from __future__ import annotations

from collections.abc import Mapping

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import PERCENTAGE
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo

from . import DOMAIN

DEVICE_INFO = DeviceInfo(
    identifiers={(DOMAIN, "BMW_STATUS_DEV_VEHICLE")},
    manufacturer="BMW",
    model="320d xDrive",
    name="BMW 320d xDrive",
)


SENSOR_DEFINITIONS = {
    "lock": ("Doors overall state", None),
    "fuel": ("Range Tank level (%)", PERCENTAGE),
    "trip_battery_charge_level_at_end_of_trip": ("Trip Battery charge level at end of trip", PERCENTAGE),
    "total_range": ("Range Total range (last sent)", "km"),
    "odometer": ("Vehicle mileage", "km"),
    "motion": ("Vehicle Motion state", None),
    "door_front_driver": ("Door state (front driver)", None),
    "door_front_passenger": ("Door state (front passenger)", None),
    "door_rear_driver": ("Door state (rear driver)", None),
    "door_rear_passenger": ("Door state (rear passenger)", None),
    "hood": ("Hood state", None),
    "tailgate": ("Tailgate state", None),
    "sunroof": ("Sunroof overall state", None),
    "sunroof_tilt": ("Sunroof tilt state", None),
    "tire": ("Tire pressure (front left)", "kPa"),
    "tire_front_right": ("Tire pressure (front right)", "kPa"),
    "tire_rear_left": ("Tire pressure (rear left)", "kPa"),
    "tire_rear_right": ("Tire pressure (rear right)", "kPa"),
    "tire_target_front_left": ("Tire Pressure Target Front Left", "kPa"),
    "tire_target_front_right": ("Tire Pressure Target Front Right", "kPa"),
    "tire_target_rear_left": ("Tire Pressure Target Rear Left", "kPa"),
    "tire_target_rear_right": ("Tire Pressure Target Rear Right", "kPa"),
    "climate": ("Preconditioning state", None),
    "climate_timer": ("Climate Timer Next-Only state", None),
}

SCENARIOS: dict[str, dict[str, str | int]] = {
    "parked": {
        "lock": "SECURED", "fuel": 88, "trip_battery_charge_level_at_end_of_trip": 68, "total_range": 744, "odometer": 18255, "motion": "off",
        "door_front_driver": "off", "door_front_passenger": "off", "door_rear_driver": "off", "door_rear_passenger": "off",
        "hood": "off", "tailgate": "off", "sunroof": "CLOSED", "sunroof_tilt": "OPEN",
        "tire": 250, "tire_front_right": 250, "tire_rear_left": 250, "tire_rear_right": 250,
        "tire_target_front_left": 230, "tire_target_front_right": 230,
        "tire_target_rear_left": 250, "tire_target_rear_right": 250,
        "climate": "INACTIVE", "climate_timer": "deactive",
    },
    "driving": {
        "lock": "SECURED", "fuel": 84, "trip_battery_charge_level_at_end_of_trip": 66, "total_range": 710, "odometer": 18272, "motion": "on",
        "door_front_driver": "off", "door_front_passenger": "off", "door_rear_driver": "off", "door_rear_passenger": "off",
        "hood": "off", "tailgate": "off", "sunroof": "CLOSED", "sunroof_tilt": "CLOSED",
        "tire": 250, "tire_front_right": 250, "tire_rear_left": 250, "tire_rear_right": 250,
        "tire_target_front_left": 230, "tire_target_front_right": 230,
        "tire_target_rear_left": 250, "tire_target_rear_right": 250,
        "climate": "INACTIVE", "climate_timer": "deactive",
    },
    "attention": {
        "lock": "UNSECURED", "fuel": 12, "trip_battery_charge_level_at_end_of_trip": 42, "total_range": 110, "odometer": 18273, "motion": "off",
        "door_front_driver": "on", "door_front_passenger": "off", "door_rear_driver": "off", "door_rear_passenger": "off",
        "hood": "off", "tailgate": "on", "sunroof": "OPEN", "sunroof_tilt": "OPEN",
        "tire": 190, "tire_front_right": 231, "tire_rear_left": 228, "tire_rear_right": 230,
        "tire_target_front_left": 230, "tire_target_front_right": 230,
        "tire_target_rear_left": 250, "tire_target_rear_right": 250,
        "climate": "ACTIVE", "climate_timer": "active",
    },
}


class CarDataFixtureSensor(SensorEntity):
    """Publish one mutable CarData-like value for the local development vehicle."""

    _attr_device_info = DEVICE_INFO
    _attr_has_entity_name = True

    def __init__(self, key: str, name: str, value: str | int, unit: str | None = None) -> None:
        """Initialize a fixture entity."""
        self._attr_unique_id = f"bmw_status_dev_{key}"
        self._attr_name = name
        self._attr_native_value = value
        self._attr_native_unit_of_measurement = unit

    def set_value(self, value: str | int) -> None:
        """Update the fixture value and publish it immediately."""
        self._attr_native_value = value
        self.async_write_ha_state()


class CarDataFixtureState:
    """Own the entities and switch them together between development scenarios."""

    def __init__(self, entities: Mapping[str, CarDataFixtureSensor]) -> None:
        """Initialize the fixture with its published entities."""
        self._entities = entities
        self.scenario = "parked"

    def async_set_scenario(self, scenario: str) -> None:
        """Apply one complete, internally consistent vehicle scenario."""
        for key, value in SCENARIOS[scenario].items():
            self._entities[key].set_value(value)
        self.scenario = scenario


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Create the fixture entities used by the BMW Status development flow."""
    registry = dr.async_get(hass)
    device = registry.async_get_device(identifiers={(DOMAIN, "BMW_STATUS_DEV_VEHICLE")})
    if device:
        registry.async_update_device(device.id, name_by_user="BMW 320d xDrive", model="320d xDrive")
    entities = {
        key: CarDataFixtureSensor(key, name, SCENARIOS["parked"][key], unit)
        for key, (name, unit) in SENSOR_DEFINITIONS.items()
    }
    async_add_entities(entities.values())
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = CarDataFixtureState(entities)