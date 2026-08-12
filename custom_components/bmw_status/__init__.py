"""BMW Status integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_MAP,
    CONF_MAP_API_KEY,
    CONF_MAP_ENABLED,
    CONF_MAP_STYLE,
    DATA_COORDINATOR,
    DOMAIN,
)
from .coordinator import BMWStatusCoordinator
from .services import async_register_services

PLATFORMS: tuple[Platform, ...] = (Platform.SENSOR,)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy backend MapTiler options into the protected map block."""
    return _migrate_maptiler_options(hass, entry)


def _migrate_maptiler_options(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Preserve legacy backend MapTiler settings during entry migration."""
    if entry.version > 4:
        return False
    options = dict(entry.options)
    legacy_key = str(options.pop("maptiler_api_key", "")).strip()
    legacy_style = str(options.pop("maptiler_style", "")).strip()
    if legacy_key and not isinstance(options.get(CONF_MAP), dict):
        options[CONF_MAP] = {
            CONF_MAP_ENABLED: True,
            CONF_MAP_API_KEY: legacy_key,
            CONF_MAP_STYLE: legacy_style or "base-v4",
        }
    if entry.version < 4 or options != entry.options:
        hass.config_entries.async_update_entry(entry, options=options, version=4)
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