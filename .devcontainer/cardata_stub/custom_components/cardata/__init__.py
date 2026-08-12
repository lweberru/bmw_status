"""Static CarData fixture used only by the BMW Status development container."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
import voluptuous as vol

DOMAIN = "cardata"
PLATFORMS = ("sensor",)
SERVICE_SET_FIXTURE_SCENARIO = "set_fixture_scenario"
SCENARIO_SCHEMA = vol.Schema({vol.Required("scenario"): vol.In(("parked", "driving", "attention"))})


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Create a local config entry without any external connection."""
    if not hass.services.has_service(DOMAIN, SERVICE_SET_FIXTURE_SCENARIO):
        async def handle_set_fixture_scenario(call: ServiceCall) -> None:
            """Switch every local fixture vehicle to a named test scenario."""
            for fixture in hass.data.get(DOMAIN, {}).values():
                fixture.async_set_scenario(call.data["scenario"])

        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_FIXTURE_SCENARIO,
            handle_set_fixture_scenario,
            schema=SCENARIO_SCHEMA,
        )
    if not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "import"},
                data={},
            )
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the local fixture entities."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the local fixture entities."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded