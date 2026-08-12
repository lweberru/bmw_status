"""Tests for BMW Status config entry migration."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bmw_status import async_migrate_entry
from custom_components.bmw_status.config_flow import BMWStatusOptionsFlow
from custom_components.bmw_status.const import (
    CONF_IMAGE,
    CONF_IMAGE_API_KEY,
    CONF_IMAGE_ENABLED,
    CONF_IMAGE_MODEL,
    CONF_IMAGE_PROVIDER,
    CONF_MAP,
    CONF_MAP_API_KEY,
    CONF_MAP_ENABLED,
    CONF_MAP_STYLE,
    DOMAIN,
)


async def test_entry_migration_preserves_backend_maptiler_options(hass):
    """Legacy backend MapTiler settings migrate into the protected map block."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        options={"maptiler_api_key": "legacy", "maptiler_style": "hybrid", "license_plate": "M-AB 1"},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.version == 4
    assert entry.options == {
        "license_plate": "M-AB 1",
        CONF_MAP: {
            CONF_MAP_ENABLED: True,
            CONF_MAP_API_KEY: "legacy",
            CONF_MAP_STYLE: "hybrid",
        },
    }


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


async def test_options_flow_skips_image_credentials_for_existing_provider_key():
    """Existing credentials do not need to be entered again while editing options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_IMAGE: {
                CONF_IMAGE_API_KEY: "existing-key",
                CONF_IMAGE_ENABLED: True,
                CONF_IMAGE_PROVIDER: "gemini",
            }
        },
    )
    flow = BMWStatusOptionsFlow(entry)
    flow._options = dict(entry.options)

    result = await flow.async_step_image_provider(
        {
            CONF_IMAGE_ENABLED: True,
            CONF_IMAGE_PROVIDER: "gemini",
            "view_mode": "auto",
            "scene_mode": "auto",
        }
    )

    assert result["type"] == "form"
    assert result["step_id"] == "map_provider"


async def test_options_flow_skips_map_credentials_for_existing_key():
    """Existing MapTiler credentials do not need to be entered again."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_MAP: {
                CONF_MAP_API_KEY: "existing-key",
                CONF_MAP_ENABLED: True,
                CONF_MAP_STYLE: "streets-v4",
            }
        },
    )
    flow = BMWStatusOptionsFlow(entry)
    flow._options = dict(entry.options)

    result = await flow.async_step_map_provider({CONF_MAP_ENABLED: True})

    assert result["type"] == "create_entry"
    assert result["data"][CONF_MAP][CONF_MAP_API_KEY] == "existing-key"