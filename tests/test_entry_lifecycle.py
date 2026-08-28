"""Tests for BMW Status config entry lifecycle."""

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bmw_status import async_setup_entry, async_unload_entry
from custom_components.bmw_status.const import CONF_CARDATA_DEVICE_ID, DATA_COORDINATOR, DOMAIN


async def test_entry_setup_and_unload_manage_coordinator_lifecycle(hass):
    """Setup forwards the sensor platform and unload stops the coordinator."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={CONF_CARDATA_DEVICE_ID: "vehicle-device"},
        options={},
    )
    entry.add_to_hass(hass)
    coordinator = AsyncMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    with (
        patch("custom_components.bmw_status.BMWStatusCoordinator", return_value=coordinator),
        patch("custom_components.bmw_status.async_register_services", new=AsyncMock()) as register_services,
    ):
        assert await async_setup_entry(hass, entry)

    register_services.assert_awaited_once_with(hass)
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    coordinator.async_start.assert_awaited_once()
    hass.config_entries.async_forward_entry_setups.assert_awaited_once()
    assert hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR] is coordinator

    assert await async_unload_entry(hass, entry)

    hass.config_entries.async_unload_platforms.assert_awaited_once()
    coordinator.async_stop.assert_awaited_once()
    assert entry.entry_id not in hass.data[DOMAIN]