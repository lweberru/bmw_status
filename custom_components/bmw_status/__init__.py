"""BMW Status integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import BMWStatusCoordinator
from .services import async_register_services

PLATFORMS: tuple[Platform, ...] = (Platform.SENSOR,)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove obsolete MapTiler options now owned by the frontend card."""
    return _migrate_maptiler_options(hass, entry)


def _migrate_maptiler_options(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove obsolete frontend-only options from an existing entry."""
    if entry.version > 2:
        return False
    options = dict(entry.options)
    options.pop("maptiler_api_key", None)
    options.pop("maptiler_style", None)
    if entry.version < 2 or options != entry.options:
        hass.config_entries.async_update_entry(entry, options=options, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BMW Status from a config entry."""
    if not _migrate_maptiler_options(hass, entry):
        return False
    await async_register_services(hass)
    coordinator = BMWStatusCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a BMW Status config entry."""
    coordinator: BMWStatusCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await coordinator.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded