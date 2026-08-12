"""Tests for BMW Status config entry migration."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bmw_status import async_migrate_entry
from custom_components.bmw_status.config_flow import BMWStatusOptionsFlow
from custom_components.bmw_status.const import (
    CONF_IMAGE,
    CONF_IMAGE_API_KEY,
    CONF_IMAGE_MODEL,
    CONF_IMAGE_PROVIDER,
    DOMAIN,
)


async def test_entry_migration_removes_maptiler_options(hass):
    """Legacy frontend MapTiler configuration is removed from the backend entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        options={"maptiler_api_key": "legacy", "maptiler_style": "hybrid", "license_plate": "M-AB 1"},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.version == 2
    assert entry.options == {"license_plate": "M-AB 1"}


async def test_options_flow_keeps_existing_image_key_when_blank():
    """Editing image settings with an empty key must not erase provider credentials."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_IMAGE: {
                CONF_IMAGE_API_KEY: "existing-key",
                CONF_IMAGE_MODEL: "old-model",
                CONF_IMAGE_PROVIDER: "gemini",
            }
        },
    )
    flow = BMWStatusOptionsFlow(entry)
    flow._options = dict(entry.options)

    result = await flow.async_step_image_credentials({CONF_IMAGE_API_KEY: "", CONF_IMAGE_MODEL: "new-model"})

    assert result["data"][CONF_IMAGE][CONF_IMAGE_API_KEY] == "existing-key"
    assert result["data"][CONF_IMAGE][CONF_IMAGE_MODEL] == "new-model"