"""Config flow for BMW Status."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CARDATA_DOMAIN,
    CONF_CARDATA_DEVICE_ID,
    CONF_IMAGE,
    CONF_IMAGE_API_KEY,
    CONF_IMAGE_ENABLED,
    CONF_IMAGE_GEOCODE_ENTITY,
    CONF_IMAGE_MODEL,
    CONF_IMAGE_PROVIDER,
    CONF_IMAGE_SCENE_MODE,
    CONF_IMAGE_SIZE,
    CONF_IMAGE_VIEW_MODE,
    CONF_LICENSE_PLATE,
    CONF_MAP,
    CONF_MAP_API_KEY,
    CONF_MAP_ENABLED,
    CONF_MAP_STYLE,
    CONF_MAP_ZOOM,
    DOMAIN,
)

IMAGE_PROVIDERS = ("gemini", "openai")
OPENAI_SIZES = ("1024x1024", "1792x1024", "1024x1792")


def _cardata_vehicle_options(hass: HomeAssistant) -> dict[str, str]:
    """Return CarData vehicle devices that currently expose at least one entity."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    device_ids = {
        entry.device_id
        for entry in entity_registry.entities.values()
        if entry.platform == CARDATA_DOMAIN and entry.device_id
    }
    options: dict[str, str] = {}
    for device_id in sorted(device_ids):
        device = device_registry.async_get(device_id)
        if device:
            options[device_id] = device.name_by_user or device.name or device_id
    return options


class BMWStatusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one BMW Status entry per CarData vehicle."""

    VERSION = 4

    def __init__(self) -> None:
        """Initialize the multi-step setup state."""
        self._vehicle: dict[str, str] = {}
        self._options: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Select the CarData vehicle to manage."""
        options = _cardata_vehicle_options(self.hass)
        if not options:
            return self.async_abort(reason="no_cardata_vehicles")

        if user_input is not None:
            device_id = str(user_input[CONF_CARDATA_DEVICE_ID])
            if device_id not in options:
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema({vol.Required(CONF_CARDATA_DEVICE_ID): vol.In(options)}),
                    errors={"base": "vehicle_not_found"},
                )

            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()
            self._vehicle = {CONF_CARDATA_DEVICE_ID: device_id, "title": options[device_id]}
            return await self.async_step_card()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_CARDATA_DEVICE_ID): vol.In(options)}),
        )

    async def async_step_card(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure optional vehicle display values."""
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_image_provider()
        return self.async_show_form(
            step_id="card",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LICENSE_PLATE, default=""): str,
                }
            ),
        )

    async def async_step_image_provider(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Select whether and how background images are generated."""
        if user_input is not None:
            self._options[CONF_IMAGE] = dict(user_input)
            if user_input[CONF_IMAGE_ENABLED]:
                return await self.async_step_image_credentials()
            return await self.async_step_map_provider()
        return self.async_show_form(
            step_id="image_provider",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IMAGE_ENABLED, default=False): bool,
                    vol.Required(CONF_IMAGE_PROVIDER, default="gemini"): vol.In(IMAGE_PROVIDERS),
                    vol.Required(CONF_IMAGE_VIEW_MODE, default="auto"): vol.In(("auto", "front_left", "rear_right")),
                    vol.Required(CONF_IMAGE_SCENE_MODE, default="auto"): vol.In(("auto", "parked", "driving")),
                    vol.Optional(CONF_IMAGE_GEOCODE_ENTITY, default=""): str,
                }
            ),
        )

    async def async_step_image_credentials(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect provider credentials and generation parameters."""
        image_options = self._options[CONF_IMAGE]
        provider = image_options[CONF_IMAGE_PROVIDER]
        if user_input is not None:
            image_options.update(user_input)
            return await self.async_step_map_provider()
        default_model = "gemini-2.5-flash-image" if provider == "gemini" else "gpt-image-1"
        schema: dict[Any, Any] = {
            vol.Required(CONF_IMAGE_API_KEY): str,
            vol.Optional(CONF_IMAGE_MODEL, default=default_model): str,
        }
        if provider == "openai":
            schema[vol.Required(CONF_IMAGE_SIZE, default="1024x1024")] = vol.In(OPENAI_SIZES)
        return self.async_show_form(step_id="image_credentials", data_schema=vol.Schema(schema))

    async def async_step_map_provider(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure an optional backend-cached static location map."""
        if user_input is not None:
            self._options[CONF_MAP] = dict(user_input)
            if user_input[CONF_MAP_ENABLED]:
                return await self.async_step_map_credentials()
            return self._async_create_config_entry()
        return self.async_show_form(
            step_id="map_provider",
            data_schema=vol.Schema({vol.Required(CONF_MAP_ENABLED, default=False): bool}),
        )

    async def async_step_map_credentials(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect MapTiler credentials that remain in backend entry options."""
        if user_input is not None:
            self._options[CONF_MAP].update(user_input)
            return self._async_create_config_entry()
        return self.async_show_form(
            step_id="map_credentials",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAP_API_KEY): str,
                    vol.Optional(CONF_MAP_STYLE, default="streets-v4"): str,
                    vol.Optional(CONF_MAP_ZOOM, default=14): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
                }
            ),
        )

    def _async_create_config_entry(self) -> ConfigFlowResult:
        """Create the selected vehicle entry with all backend options."""
        return self.async_create_entry(
            title=self._vehicle["title"],
            data={CONF_CARDATA_DEVICE_ID: self._vehicle[CONF_CARDATA_DEVICE_ID]},
            options=self._options,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the BMW Status options flow."""
        return BMWStatusOptionsFlow(config_entry)


class BMWStatusOptionsFlow(OptionsFlow):
    """Edit BMW Status backend and provider configuration."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit non-sensitive vehicle options."""
        if user_input is not None:
            self._options = {**self._config_entry.options, **user_input}
            return await self.async_step_image_provider()
        options = self._config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LICENSE_PLATE, default=options.get(CONF_LICENSE_PLATE, "")): str,
                }
            ),
        )

    async def async_step_image_provider(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit the image provider mode."""
        current = dict(self._options.get(CONF_IMAGE) or {})
        if user_input is not None:
            image = {**current, **user_input}
            replace_key = bool(image.pop("replace_api_key", False))
            self._options[CONF_IMAGE] = image
            provider_changed = image[CONF_IMAGE_PROVIDER] != current.get(CONF_IMAGE_PROVIDER)
            has_key = bool(str(image.get(CONF_IMAGE_API_KEY) or "").strip())
            if image[CONF_IMAGE_ENABLED] and (replace_key or provider_changed or not has_key):
                return await self.async_step_image_credentials()
            return await self.async_step_map_provider()
        return self.async_show_form(
            step_id="image_provider",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IMAGE_ENABLED, default=current.get(CONF_IMAGE_ENABLED, False)): bool,
                    vol.Required(CONF_IMAGE_PROVIDER, default=current.get(CONF_IMAGE_PROVIDER, "gemini")): vol.In(IMAGE_PROVIDERS),
                    vol.Required(CONF_IMAGE_VIEW_MODE, default=current.get(CONF_IMAGE_VIEW_MODE, "auto")): vol.In(("auto", "front_left", "rear_right")),
                    vol.Required(CONF_IMAGE_SCENE_MODE, default=current.get(CONF_IMAGE_SCENE_MODE, "auto")): vol.In(("auto", "parked", "driving")),
                    vol.Optional(CONF_IMAGE_GEOCODE_ENTITY, default=current.get(CONF_IMAGE_GEOCODE_ENTITY, "")): str,
                    vol.Optional("replace_api_key", default=False): bool,
                }
            ),
        )

    async def async_step_image_credentials(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit image credentials while preserving an existing key if blank."""
        image = self._options[CONF_IMAGE]
        provider = image[CONF_IMAGE_PROVIDER]
        if user_input is not None:
            key = str(user_input.pop(CONF_IMAGE_API_KEY, "")).strip()
            if key:
                image[CONF_IMAGE_API_KEY] = key
            image.update(user_input)
            return await self.async_step_map_provider()
        default_model = image.get(CONF_IMAGE_MODEL) or (
            "gemini-2.5-flash-image" if provider == "gemini" else "gpt-image-1"
        )
        schema: dict[Any, Any] = {
            vol.Optional(CONF_IMAGE_API_KEY, default=""): str,
            vol.Optional(CONF_IMAGE_MODEL, default=default_model): str,
        }
        if provider == "openai":
            schema[vol.Required(CONF_IMAGE_SIZE, default=image.get(CONF_IMAGE_SIZE, "1024x1024"))] = vol.In(OPENAI_SIZES)
        return self.async_show_form(step_id="image_credentials", data_schema=vol.Schema(schema))

    async def async_step_map_provider(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit the backend-cached static location map configuration."""
        current = dict(self._options.get(CONF_MAP) or {})
        if user_input is not None:
            map_options = {**current, **user_input}
            replace_key = bool(map_options.pop("replace_api_key", False))
            self._options[CONF_MAP] = map_options
            has_key = bool(str(map_options.get(CONF_MAP_API_KEY) or "").strip())
            if map_options[CONF_MAP_ENABLED] and (replace_key or not has_key):
                return await self.async_step_map_credentials()
            return self.async_create_entry(title="", data=self._options)
        return self.async_show_form(
            step_id="map_provider",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAP_ENABLED, default=current.get(CONF_MAP_ENABLED, False)): bool,
                    vol.Optional("replace_api_key", default=False): bool,
                }
            ),
        )

    async def async_step_map_credentials(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit MapTiler credentials without exposing an existing key."""
        map_options = self._options[CONF_MAP]
        if user_input is not None:
            key = str(user_input.pop(CONF_MAP_API_KEY, "")).strip()
            if key:
                map_options[CONF_MAP_API_KEY] = key
            map_options.update(user_input)
            return self.async_create_entry(title="", data=self._options)
        return self.async_show_form(
            step_id="map_credentials",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_MAP_API_KEY, default=""): str,
                    vol.Optional(CONF_MAP_STYLE, default=map_options.get(CONF_MAP_STYLE, "streets-v4")): str,
                    vol.Optional(CONF_MAP_ZOOM, default=map_options.get(CONF_MAP_ZOOM, 14)): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
                }
            ),
        )