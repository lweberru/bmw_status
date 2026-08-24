"""Local vehicle-position fixture for BMW Status development."""

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.helpers.entity import DeviceInfo

from . import DOMAIN


async def async_setup_entry(_hass, entry, async_add_entities) -> None:
    """Publish one fixed vehicle location on the CarData fixture device."""
    async_add_entities([CarDataFixtureTracker(entry.entry_id)], update_before_add=True)


class CarDataFixtureTracker(TrackerEntity):
    """Expose a deterministic position for map rendering tests."""

    _attr_name = "Vehicle Position"
    _attr_source_type = "gps"
    _attr_latitude = 48.9918286111
    _attr_longitude = 9.1283355556
    _attr_extra_state_attributes = {"gps_altitude": 272.4, "gps_altitude_unit": "m"}

    async def async_update(self) -> None:
        """Keep a GPS state available after Home Assistant restarts."""
        return None

    def __init__(self, entry_id: str) -> None:
        self._attr_unique_id = "bmw_status_dev_vehicle_position"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "BMW_STATUS_DEV_VEHICLE")},
            manufacturer="BMW",
            model="Development Vehicle",
            name="BMW Status Dev Vehicle",
        )