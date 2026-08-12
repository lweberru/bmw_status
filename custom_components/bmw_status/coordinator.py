"""Coordinator for the BMW Status presentation."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CARDATA_DOMAIN,
    CONF_CARDATA_DEVICE_ID,
    CONF_IMAGE,
    CONF_IMAGE_ENABLED,
    CONF_LICENSE_PLATE,
    DOMAIN,
    PRESENTATION_SCHEMA_VERSION,
)
from .image_jobs import ImageJobManager, ImageJobState, presentation_key
from .image_provider import ImageProviderConfig, async_generate_state_render
from .image_store import ImageStore
from .presentation import EntitySnapshot, build_presentation

_LOGGER = logging.getLogger(__name__)


class BMWStatusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Own the published presentation for one configured vehicle."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator without periodic polling."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{entry.entry_id}",
        )
        self.entry = entry
        self._unsub_state_changes: Callable[[], None] | None = None
        self._image_state = ImageJobState("disabled")
        self._image_store = ImageStore(hass, entry.entry_id)
        self._image_index: dict[str, Any] = {"version": 1, "images": {}}
        self._image_jobs = ImageJobManager(hass, self._async_render_image, self._publish_image_state)

    async def async_start(self) -> None:
        """Subscribe to the current CarData entities for this vehicle."""
        self._image_index = await self._image_store.async_load(self.hass)
        entity_ids = [snapshot.entity_id for snapshot in self._entity_snapshots(self.entry.data[CONF_CARDATA_DEVICE_ID])]
        self._unsub_state_changes = async_track_state_change_event(self.hass, entity_ids, self._async_handle_state_change)
        await self.async_request_refresh()

    async def async_stop(self) -> None:
        """Remove subscriptions and pending image work."""
        if self._unsub_state_changes:
            self._unsub_state_changes()
            self._unsub_state_changes = None
        self._image_jobs.async_shutdown()

    @callback
    def _async_handle_state_change(self, _event: Event) -> None:
        """Refresh immediately, then request a debounced image for the new state."""
        self.hass.async_create_task(self.async_request_refresh())

    def _publish_image_state(self, state: ImageJobState) -> None:
        """Publish asynchronous job state without rebuilding the vehicle snapshot."""
        self._image_state = state
        if self.data:
            next_data = dict(self.data)
            next_data["image_status"] = state.status
            next_data["error"] = state.error
            next_data["retry_after"] = state.retry_after
            self.async_set_updated_data(next_data)

    async def _async_render_image(self, state_key: str) -> None:
        """Render the latest state and persist its image plus cache metadata."""
        config = self._image_config()
        if not config:
            return
        presentation = (self.data or {}).get("presentation") or {}
        prompt = self._build_state_render_prompt(presentation)
        image = await async_generate_state_render(self.hass, config, prompt)
        filename = f"state-{state_key}.png"
        local_url = await self._image_store.async_write_png(self.hass, filename, image)
        self._image_index.setdefault("images", {})[state_key] = {
            "filename": filename,
            "local_url": local_url,
            "status": "ready",
            "prompt": prompt,
            "provider": config.provider,
            "model": config.model,
            "updated_at": _utc_timestamp(),
        }
        await self._image_store.async_save(self.hass, self._image_index)
        await self.async_request_refresh()

    async def async_regenerate_images(self) -> None:
        """Force regeneration of the current state when image generation is enabled."""
        if not self._image_config() or not self.data:
            return
        state_key = presentation_key(self.data.get("presentation") or {})
        self._image_index.get("images", {}).pop(state_key, None)
        await self._image_store.async_save(self.hass, self._image_index)
        self._image_jobs.async_request(state_key, force=True)

    async def async_clear_image_cache(self) -> None:
        """Clear this vehicle's image cache without affecting other entries."""
        await self._image_store.async_clear(self.hass)
        self._image_index = {"version": 1, "images": {}}
        self._image_state = ImageJobState("disabled" if not self._image_config() else "pending")
        await self.async_request_refresh()

    def _image_config(self) -> ImageProviderConfig | None:
        """Read Phase-4 provider settings without publishing secrets."""
        options = self.entry.options.get("image")
        if not isinstance(options, dict):
            return None
        if not options.get(CONF_IMAGE_ENABLED, False):
            return None
        provider = str(options.get("provider") or "")
        api_key = str(options.get("api_key") or "")
        if provider not in {"gemini", "openai"} or not api_key:
            return None
        default_model = "gemini-2.5-flash-image" if provider == "gemini" else "gpt-image-1"
        return ImageProviderConfig(
            provider=provider,
            api_key=api_key,
            model=str(options.get("model") or default_model),
            size=str(options.get("size") or "1024x1024"),
        )

    def _build_state_render_prompt(self, presentation: dict[str, Any]) -> str:
        """Build a full-frame prompt from the semantic presentation."""
        vehicle = presentation.get("vehicle") or {}
        status = presentation.get("status") or {}
        name = str(vehicle.get("name") or "BMW")
        model = str(vehicle.get("model") or "").strip()
        image_options = self.entry.options.get(CONF_IMAGE) or {}
        configured_scene = image_options.get("scene_mode", "auto")
        scene_key = status.get("key") if configured_scene == "auto" else configured_scene
        scene = "driving on a road" if scene_key == "driving" else "parked in a realistic parking environment"
        configured_view = image_options.get("view_mode", "auto")
        view = "rear three-quarter view" if configured_view == "rear_right" else "front three-quarter view"
        open_names = [
            str(item.get("name") or item.get("entity_id"))
            for item in ((presentation.get("groups") or {}).get("doors") or [])
            if str(item.get("state") or "").lower() in {"on", "true", "open", "opened"}
        ]
        openings = f"Open only: {', '.join(open_names)}." if open_names else "Keep all doors, windows, hood, trunk and sunroof closed."
        return (
            f"Full-frame photorealistic {view} image of {name} {model}, {scene}. "
            f"Keep the same vehicle identity, camera framing and background. {openings} "
            "Use vehicle-relative left and right; do not mirror the vehicle."
        ).replace("  ", " ").strip()

    async def _async_update_data(self) -> dict[str, Any]:
        """Build the current presentation from the configured CarData device."""
        device_id = self.entry.data[CONF_CARDATA_DEVICE_ID]
        vehicle = self._vehicle_metadata(device_id)
        entities = self._entity_snapshots(device_id)
        presentation = build_presentation(vehicle, entities)
        state_key = presentation_key(presentation)
        cached_image = self._image_index.get("images", {}).get(state_key)
        image_configured = self._image_config() is not None
        if image_configured and cached_image and await self._image_store.async_exists(self.hass, str(cached_image.get("filename") or "")):
            presentation["images"] = [str(cached_image["local_url"])]
            self._image_state = ImageJobState("ready")
        elif image_configured:
            self._image_jobs.async_request(state_key)
        else:
            self._image_state = ImageJobState("disabled")
        return {
            "schema_version": PRESENTATION_SCHEMA_VERSION,
            "presentation": presentation,
            "image_status": self._image_state.status,
            "updated_at": _utc_timestamp(),
            "error": self._image_state.error,
            "retry_after": self._image_state.retry_after,
        }

    def _vehicle_metadata(self, device_id: str) -> dict[str, str | None]:
        """Return serializable metadata for the selected CarData device."""
        device = dr.async_get(self.hass).async_get(device_id)
        if not device:
            return {"device_id": device_id, "name": device_id, "manufacturer": None, "model": None}
        return {
            "device_id": device_id,
            "name": device.name_by_user or device.name or device_id,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "license_plate": self.entry.options.get(CONF_LICENSE_PLATE) or None,
        }

    def _entity_snapshots(self, device_id: str) -> list[EntitySnapshot]:
        """Collect current states for the selected CarData device only."""
        registry = er.async_get(self.hass)
        snapshots: list[EntitySnapshot] = []
        for entry in registry.entities.values():
            if entry.platform != CARDATA_DOMAIN or entry.device_id != device_id:
                continue
            state = self.hass.states.get(entry.entity_id)
            if not state:
                continue
            snapshots.append(
                EntitySnapshot(
                    entity_id=entry.entity_id,
                    state=state.state,
                    name=str(state.attributes.get("friendly_name") or entry.entity_id),
                    device_class=state.attributes.get("device_class"),
                    unit=state.attributes.get("unit_of_measurement"),
                )
            )
        return snapshots


def _utc_timestamp() -> str:
    """Return an ISO timestamp suitable for an entity attribute."""
    now: datetime = dt_util.utcnow()
    return now.isoformat()