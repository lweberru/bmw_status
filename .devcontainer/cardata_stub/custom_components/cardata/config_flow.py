"""Config flow for the local CarData development fixture."""

from __future__ import annotations

from homeassistant import config_entries

from . import DOMAIN


class CarDataFixtureConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the single local vehicle fixture."""

    VERSION = 1

    async def async_step_import(self, _import_data: dict) -> config_entries.ConfigFlowResult:
        """Create the fixture from the development YAML configuration."""
        await self.async_set_unique_id("BMW_STATUS_DEV_VEHICLE")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="BMW Status Dev Vehicle", data={})