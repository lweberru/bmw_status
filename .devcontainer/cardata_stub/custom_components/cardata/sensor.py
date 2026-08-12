"""Mutable vehicle entities for exercising BMW Status locally."""

from __future__ import annotations

from collections.abc import Mapping

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.entity import DeviceInfo

from . import DOMAIN

DEVICE_INFO = DeviceInfo(
    identifiers={(DOMAIN, "BMW_STATUS_DEV_VEHICLE")},
    manufacturer="BMW",
    model="Development Vehicle",
    name="BMW Status Dev Vehicle",
)


SENSOR_DEFINITIONS = {
    "lock": ("Lock Status", None),
    "charging": ("Charging Status", None),
    "soc": ("State of Charge", PERCENTAGE),
    "fuel": ("Remaining Fuel", "L"),
    "electric_range": ("Remaining Electric Range", "km"),
    "total_range": ("Remaining Range", "km"),
    "odometer": ("Travelled Distance", "km"),
    "motion": ("Vehicle Motion State", None),
    "door": ("Driver Door", None),
    "passenger_door": ("Passenger Door", None),
    "tailgate": ("Tailgate", None),
    "tire": ("Tire Pressure Front Left", "kPa"),
    "tire_front_right": ("Tire Pressure Front Right", "kPa"),
    "tire_rear_left": ("Tire Pressure Rear Left", "kPa"),
    "tire_rear_right": ("Tire Pressure Rear Right", "kPa"),
    "service": ("Condition Based Service", None),
    "climate": ("Preconditioning", None),
}

SCENARIOS: dict[str, dict[str, str | int]] = {
    "parked": {
        "lock": "locked", "charging": "off", "soc": 78, "fuel": 42,
        "electric_range": 48, "total_range": 560, "odometer": 22450, "motion": "parked",
        "door": "off", "passenger_door": "off", "tailgate": "off",
        "tire": 235, "tire_front_right": 234, "tire_rear_left": 231, "tire_rear_right": 232,
        "service": "normal", "climate": "off",
    },
    "driving": {
        "lock": "locked", "charging": "off", "soc": 65, "fuel": 38,
        "electric_range": 39, "total_range": 510, "odometer": 22467, "motion": "driving",
        "door": "off", "passenger_door": "off", "tailgate": "off",
        "tire": 239, "tire_front_right": 238, "tire_rear_left": 235, "tire_rear_right": 236,
        "service": "normal", "climate": "on",
    },
    "attention": {
        "lock": "unlocked", "charging": "off", "soc": 18, "fuel": 8,
        "electric_range": 9, "total_range": 70, "odometer": 22468, "motion": "parked",
        "door": "on", "passenger_door": "off", "tailgate": "on",
        "tire": 190, "tire_front_right": 231, "tire_rear_left": 228, "tire_rear_right": 230,
        "service": "service due", "climate": "off",
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
    entities = {
        key: CarDataFixtureSensor(key, name, SCENARIOS["parked"][key], unit)
        for key, (name, unit) in SENSOR_DEFINITIONS.items()
    }
    async_add_entities(entities.values())
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = CarDataFixtureState(entities)