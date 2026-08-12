"""Local image metadata storage for BMW Status."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

from homeassistant.core import HomeAssistant


class ImageStore:
    """Own one vehicle's image directory and JSON cache index."""

    def __init__(self, hass: HomeAssistant, vehicle_key: str) -> None:
        """Initialize the isolated `/config/www/bmw_status` directory."""
        safe_key = "".join(char for char in vehicle_key if char.isalnum() or char in "-_")
        self._directory = Path(hass.config.path("www", "bmw_status", safe_key))
        self._index = self._directory / "index.json"

    async def async_load(self, hass: HomeAssistant) -> dict[str, Any]:
        """Load the image index off the event loop."""
        return await hass.async_add_executor_job(self._load)

    async def async_save(self, hass: HomeAssistant, index: dict[str, Any]) -> None:
        """Persist an index atomically off the event loop."""
        await hass.async_add_executor_job(self._save, index)

    async def async_write_png(self, hass: HomeAssistant, filename: str, image: bytes) -> str:
        """Atomically write a PNG and return its Home Assistant local URL."""
        await hass.async_add_executor_job(self._write_png, filename, image)
        return f"/local/bmw_status/{self._directory.name}/{filename}"

    async def async_exists(self, hass: HomeAssistant, filename: str) -> bool:
        """Return whether an indexed image file still exists."""
        return await hass.async_add_executor_job(lambda: (self._directory / filename).is_file())

    async def async_clear(self, hass: HomeAssistant) -> None:
        """Delete only this vehicle's image directory off the event loop."""
        await hass.async_add_executor_job(lambda: shutil.rmtree(self._directory, ignore_errors=True))

    def _load(self) -> dict[str, Any]:
        if not self._index.exists():
            return {"version": 1, "images": {}}
        try:
            return json.loads(self._index.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "images": {}}

    def _save(self, index: dict[str, Any]) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        temporary = self._index.with_suffix(".tmp")
        temporary.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self._index)

    def _write_png(self, filename: str, image: bytes) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        destination = self._directory / filename
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(image)
        temporary.replace(destination)