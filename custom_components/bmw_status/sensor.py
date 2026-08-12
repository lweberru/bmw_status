"""Status sensor for BMW Status."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CARDATA_DEVICE_ID, DATA_COORDINATOR, DOMAIN
from .coordinator import BMWStatusCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the BMW Status sensor for one vehicle."""
    coordinator: BMWStatusCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities([BMWStatusSensor(entry, coordinator)])


class BMWStatusSensor(CoordinatorEntity[BMWStatusCoordinator], SensorEntity):
    """Publish the versioned BMW presentation contract."""

    _attr_has_entity_name = True
    _attr_name = "Status"
    _attr_icon = "mdi:car-info"

    def __init__(self, entry: ConfigEntry, coordinator: BMWStatusCoordinator) -> None:
        """Initialize the status sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._cardata_device_id = entry.data[CONF_CARDATA_DEVICE_ID]

    @property
    def native_value(self) -> str:
        """Return the normalized vehicle state from the presentation."""
        status = (self.coordinator.data or {}).get("presentation", {}).get("status", {})
        return str(status.get("key") or "unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the presentation contract for the frontend card."""
        return dict(self.coordinator.data or {})