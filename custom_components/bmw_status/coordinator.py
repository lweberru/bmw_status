"""Coordinator for the BMW Status presentation."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
import logging
import math
import ssl
from typing import Any, Callable
from urllib.parse import quote, urlencode

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from PIL import Image

from .const import (
    CARDATA_DOMAIN,
    CONF_CARDATA_DEVICE_ID,
    CONF_IMAGE,
    CONF_IMAGE_ENABLED,
    CONF_LICENSE_PLATE,
    CONF_MAP,
    CONF_MAP_API_KEY,
    CONF_MAP_ENABLED,
    CONF_MAP_STYLE,
    CONF_MAP_ZOOM,
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
        self._map_jobs = ImageJobManager(hass, self._async_render_image, self._publish_image_state)

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
        self._map_jobs.async_shutdown()

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
        presentation = (self.data or {}).get("presentation") or {}
        if state_key.startswith("map-"):
            map_config = self._map_config()
            if not map_config:
                return
            image = await self._async_fetch_location_map(map_config, presentation)
            prompt = "MapTiler static location map"
            asset = "map"
            provider = "maptiler"
            model = str(map_config["style"])
        else:
            config = self._image_config()
            if not config:
                return
            is_tire_render = state_key.startswith("tire-")
            prompt = self._build_tire_render_prompt(presentation) if is_tire_render else self._build_state_render_prompt(presentation)
            image = await async_generate_state_render(self.hass, config, prompt)
            asset = "tire" if is_tire_render else "state"
            provider = config.provider
            model = config.model
        filename = f"{asset}-{state_key}.png"
        local_url = await self._image_store.async_write_png(self.hass, filename, image)
        self._image_index.setdefault("images", {})[state_key] = {
            "filename": filename,
            "local_url": local_url,
            "status": "ready",
            "prompt": prompt,
            "provider": provider,
            "model": model,
            "updated_at": _utc_timestamp(),
        }
        await self._image_store.async_save(self.hass, self._image_index)
        await self.async_request_refresh()

    async def async_regenerate_images(self) -> None:
        """Force regeneration of the current state when image generation is enabled."""
        if not self.data:
            return
        presentation = self.data.get("presentation") or {}
        state_key = f"state-{presentation_key(presentation)}"
        tire_key = f"tire-{presentation_key({'vehicle': presentation.get('vehicle') or {}, 'asset': 'tire_top_down'})}"
        map_key = self._location_map_key(presentation)
        if self._image_config():
            self._image_index.get("images", {}).pop(state_key, None)
            self._image_index.get("images", {}).pop(tire_key, None)
            self._image_jobs.async_request(state_key, force=True)
            self._image_jobs.async_request(tire_key, force=True)
        if self._map_config() and map_key:
            self._image_index.get("images", {}).pop(map_key, None)
            self._map_jobs.async_request(map_key, force=True)
        await self._image_store.async_save(self.hass, self._image_index)

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

    def _map_config(self) -> dict[str, Any] | None:
        """Read MapTiler credentials kept only in config-entry options."""
        options = self.entry.options.get(CONF_MAP)
        if not isinstance(options, dict) or not options.get(CONF_MAP_ENABLED):
            return None
        api_key = str(options.get(CONF_MAP_API_KEY) or "").strip()
        if not api_key:
            return None
        return {
            "api_key": api_key,
            "style": str(options.get(CONF_MAP_STYLE) or "streets-v4").strip(),
            "zoom": int(options.get(CONF_MAP_ZOOM) or 14),
        }

    def _location_map_key(self, presentation: dict[str, Any]) -> str | None:
        """Build a cache key from the current location and requested map style."""
        config = self._map_config()
        tracker = (presentation.get("entities") or {}).get("device_tracker") or {}
        latitude = tracker.get("latitude")
        longitude = tracker.get("longitude")
        if not config or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            return None
        return f"map-{presentation_key({'renderer_version': 2, 'latitude': latitude, 'longitude': longitude, 'style': config['style'], 'zoom': config['zoom']})}"

    async def _async_fetch_location_map(self, config: dict[str, Any], presentation: dict[str, Any]) -> bytes:
        """Build a static map from server-fetched tiles without exposing the API key."""
        tracker = (presentation.get("entities") or {}).get("device_tracker") or {}
        latitude = tracker.get("latitude")
        longitude = tracker.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            raise RuntimeError("Vehicle location is unavailable for the map")
        zoom = int(config["zoom"])
        tile_count = 2**zoom
        world_x = (longitude + 180) / 360 * tile_count
        latitude_radians = math.radians(max(min(latitude, 85.05112878), -85.05112878))
        world_y = (1 - math.asinh(math.tan(latitude_radians)) / math.pi) / 2 * tile_count
        center_x = math.floor(world_x)
        center_y = math.floor(world_y)
        style = quote(str(config["style"]), safe="-")
        query = urlencode({"key": config["api_key"]})
        session = aiohttp_client.async_get_clientsession(self.hass)
        ssl_context = ssl.create_default_context()
        tile_image: Image.Image | None = None
        tile_size: int | None = None
        for row, tile_y in enumerate(range(center_y - 2, center_y + 3)):
            clamped_y = min(max(tile_y, 0), tile_count - 1)
            for column, tile_x in enumerate(range(center_x - 2, center_x + 3)):
                wrapped_x = tile_x % tile_count
                url = f"https://api.maptiler.com/maps/{style}/{zoom}/{wrapped_x}/{clamped_y}.png?{query}"
                async with session.get(url, ssl=ssl_context) as response:
                    if response.status >= 400:
                        raise RuntimeError(f"MapTiler tile failed: {response.status}")
                    image = Image.open(BytesIO(await response.read())).convert("RGB")
                if image.width != image.height:
                    raise RuntimeError(f"MapTiler returned a non-square tile: {image.size}")
                if tile_size is None:
                    tile_size = image.width
                    tile_image = Image.new("RGB", (tile_size * 5, tile_size * 5))
                elif image.size != (tile_size, tile_size):
                    raise RuntimeError(f"MapTiler returned inconsistent tile sizes: {image.size}")
                assert tile_image is not None
                tile_image.paste(image, (column * tile_size, row * tile_size))
        if tile_image is None or tile_size is None:
            raise RuntimeError("MapTiler returned no tiles")
        pixel_x = (world_x - center_x + 2) * tile_size
        pixel_y = (world_y - center_y + 2) * tile_size
        crop = tile_image.crop((round(pixel_x - 320), round(pixel_y - 140), round(pixel_x + 320), round(pixel_y + 140)))
        output = BytesIO()
        crop.save(output, format="PNG")
        return output.getvalue()

    def _build_state_render_prompt(self, presentation: dict[str, Any]) -> str:
        """Build a full-frame prompt from the semantic presentation."""
        vehicle = presentation.get("vehicle") or {}
        status = presentation.get("status") or {}
        identity = " ".join(
            str(vehicle.get(field) or "").strip()
            for field in ("year", "color", "manufacturer", "model", "series", "trim", "body")
            if str(vehicle.get(field) or "").strip()
        ) or str(vehicle.get("name") or "BMW")
        license_plate = str(vehicle.get("license_plate") or "").strip()
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
        identity_lock = (
            f"This must be exactly this vehicle identity: {identity}. "
            "Do not change its manufacturer, model family, body shape, paint color, trim, badges or wheel design."
        )
        plate_instruction = f"License plate text must remain exactly: {license_plate}." if license_plate else ""
        return (
            f"Full-frame photorealistic {view} image of {identity}, {scene}. "
            f"{identity_lock} {plate_instruction} Keep the same camera framing and background. {openings} "
            "Use vehicle-relative left and right; do not mirror the vehicle."
        ).replace("  ", " ").strip()

    def _build_tire_render_prompt(self, presentation: dict[str, Any]) -> str:
        """Build a stable, top-down vehicle reference image for tire placement."""
        vehicle = presentation.get("vehicle") or {}
        identity = " ".join(
            str(vehicle.get(field) or "").strip()
            for field in ("year", "color", "manufacturer", "model", "series", "trim", "body")
            if str(vehicle.get(field) or "").strip()
        ) or str(vehicle.get("name") or "BMW")
        return (
            f"Photorealistic true top-down orthographic studio image of exactly this vehicle: {identity}. "
            "Show the complete car centered, with all four wheels fully visible, vehicle front at the top, "
            "on a plain transparent or light neutral background. No people, text, labels, shadows, scenery, "
            "cut-off parts, perspective view, or mirrored orientation."
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Build the current presentation from the configured CarData device."""
        device_id = self.entry.data[CONF_CARDATA_DEVICE_ID]
        vehicle = self._vehicle_metadata(device_id)
        entities = self._entity_snapshots(device_id)
        presentation = build_presentation(vehicle, entities)
        state_key = f"state-{presentation_key(presentation)}"
        tire_key = f"tire-{presentation_key({'vehicle': presentation.get('vehicle') or {}, 'asset': 'tire_top_down'})}"
        cached_image = self._image_index.get("images", {}).get(state_key)
        cached_tire_image = self._image_index.get("images", {}).get(tire_key)
        map_key = self._location_map_key(presentation)
        cached_map_image = self._image_index.get("images", {}).get(map_key) if map_key else None
        image_configured = self._image_config() is not None
        if image_configured and cached_image and await self._image_store.async_exists(self.hass, str(cached_image.get("filename") or "")):
            presentation["images"] = [str(cached_image["local_url"])]
            self._image_state = ImageJobState("ready")
        elif image_configured:
            self._image_jobs.async_request(state_key)
        else:
            self._image_state = ImageJobState("disabled")
        if image_configured and cached_tire_image and await self._image_store.async_exists(self.hass, str(cached_tire_image.get("filename") or "")):
            presentation["tire_image"] = str(cached_tire_image["local_url"])
        elif image_configured:
            self._image_jobs.async_request(tire_key)
        if map_key and cached_map_image and await self._image_store.async_exists(self.hass, str(cached_map_image.get("filename") or "")):
            presentation["location_image"] = str(cached_map_image["local_url"])
        elif map_key:
            self._map_jobs.async_request(map_key)
        elif not image_configured:
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
        metadata: dict[str, str | None] = {
            "device_id": device_id,
            "name": device.name_by_user or device.name or device_id,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "series": None,
            "year": None,
            "color": None,
            "trim": None,
            "body": None,
            "license_plate": None,
        }
        for snapshot in self._entity_snapshots(device_id):
            attributes = snapshot.attributes or {}
            basic = attributes.get("vehicle_basic_data") or attributes.get("vehicleBasicData")
            raw = attributes.get("vehicle_basic_data_raw") or attributes.get("vehicleBasicDataRaw")
            if isinstance(basic, dict):
                self._merge_vehicle_metadata(metadata, basic, raw=False)
            if isinstance(raw, dict):
                self._merge_vehicle_metadata(metadata, raw, raw=True)
        metadata["license_plate"] = str(self.entry.options.get(CONF_LICENSE_PLATE) or metadata["license_plate"] or "").strip() or None
        return metadata

    @staticmethod
    def _merge_vehicle_metadata(metadata: dict[str, str | None], values: dict[str, Any], *, raw: bool) -> None:
        """Fill missing vehicle identity fields from CarData's basic-data variants."""
        fields = (
            {
                "manufacturer": ("brand",),
                "model": ("modelName", "modelRange", "series", "seriesDevt"),
                "series": ("series", "seriesDevt"),
                "year": ("constructionDate",),
                "color": ("colourDescription", "colourCodeRaw"),
                "trim": ("trim", "package", "edition"),
                "body": ("bodyType",),
                "license_plate": ("licensePlate", "license_plate", "registrationNumber"),
            }
            if raw
            else {
                "model": ("model_name",),
                "series": ("series",),
                "year": ("construction_date",),
                "color": ("color",),
                "trim": ("trim", "package", "edition"),
                "body": ("body_type",),
                "license_plate": ("license_plate", "licensePlate", "registration_number"),
            }
        )
        for target, sources in fields.items():
            if metadata.get(target):
                continue
            for source in sources:
                value = str(values.get(source) or "").strip()
                if value:
                    metadata[target] = value[:4] if target == "year" else value
                    break

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
                    attributes=dict(state.attributes),
                )
            )
        return snapshots


def _utc_timestamp() -> str:
    """Return an ISO timestamp suitable for an entity attribute."""
    now: datetime = dt_util.utcnow()
    return now.isoformat()