"""Background image job coordination for BMW Status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
import hashlib
import json
import logging
from typing import Any, Awaitable, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class ImageErrorKind(StrEnum):
    """Error categories used to decide whether a retry is safe."""

    AUTHENTICATION = "authentication"
    CONFIGURATION = "configuration"
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    PROVIDER = "provider"
    QUOTA = "quota"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class ImageJobState:
    """Published, serializable state of one vehicle image job."""

    status: str
    error: str | None = None
    retry_after: str | None = None


class ImageJobManager:
    """Serialize image requests and coalesce quick state changes per vehicle."""

    def __init__(
        self,
        hass: HomeAssistant,
        render: Callable[[str], Awaitable[None]],
        publish: Callable[[ImageJobState], None],
        debounce_seconds: float = 5,
    ) -> None:
        """Initialize a job manager with a rendering callback."""
        self._hass = hass
        self._render = render
        self._publish = publish
        self._debounce_seconds = debounce_seconds
        self._active = False
        self._pending_keys: list[str] = []
        self._scheduled_cancel: Callable[[], None] | None = None
        self._retry_after: str | None = None
        self._retry_attempts: dict[str, int] = {}

    def async_request(self, state_key: str, *, force: bool = False) -> None:
        """Queue the newest distinct state and debounce its render request."""
        retry_at = dt_util.parse_datetime(self._retry_after) if self._retry_after else None
        if not force and retry_at and retry_at > dt_util.utcnow():
            self._publish(ImageJobState("error", "Bildgenerierung wartet auf Provider-Kontingent.", self._retry_after))
            return
        if state_key in self._pending_keys and not force:
            return
        if force:
            self._pending_keys = [key for key in self._pending_keys if key != state_key]
        self._pending_keys.append(state_key)
        if self._scheduled_cancel:
            self._scheduled_cancel()
        self._scheduled_cancel = async_call_later(self._hass, self._debounce_seconds, self._async_start)
        self._publish(ImageJobState("pending"))

    async def _async_start(self, _now: Any) -> None:
        """Render one state; retain only the newest request while it is active."""
        self._scheduled_cancel = None
        if self._active or not self._pending_keys:
            return
        key = self._pending_keys.pop(0)
        self._active = True
        retry_scheduled = False
        try:
            await self._render(key)
            self._retry_after = None
            self._retry_attempts.pop(key, None)
            self._publish(ImageJobState("ready"))
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Asset render failed for %s: %s", key, _safe_error_message(err))
            kind = classify_image_error(err)
            retry_after = self._set_retry_after(kind)
            self._publish(ImageJobState("error", _safe_error_message(err), retry_after))
            attempts = self._retry_attempts.get(key, 0) + 1
            self._retry_attempts[key] = attempts
            if kind in {ImageErrorKind.NETWORK, ImageErrorKind.PROVIDER, ImageErrorKind.TIMEOUT} and attempts <= 3:
                self._pending_keys.insert(0, key)
                delay = 15 * (2 ** (attempts - 1))
                self._scheduled_cancel = async_call_later(self._hass, delay, self._async_start)
                retry_scheduled = True
        finally:
            self._active = False
            if self._pending_keys and not retry_scheduled:
                self._scheduled_cancel = async_call_later(self._hass, 0, self._async_start)

    def _set_retry_after(self, kind: ImageErrorKind) -> str | None:
        """Return a retry deadline only for errors that must block jobs."""
        if kind is ImageErrorKind.QUOTA:
            retry_after = dt_util.utcnow() + timedelta(hours=1)
            self._retry_after = retry_after.isoformat()
            return self._retry_after
        if kind in {ImageErrorKind.AUTHENTICATION, ImageErrorKind.CONFIGURATION, ImageErrorKind.FILESYSTEM}:
            self._retry_after = None
        return None

    def async_shutdown(self) -> None:
        """Cancel the delayed job while the config entry unloads."""
        if self._scheduled_cancel:
            self._scheduled_cancel()
            self._scheduled_cancel = None


def presentation_key(presentation: dict[str, Any]) -> str:
    """Hash only semantic display state to deduplicate equivalent requests."""
    payload = json.dumps(presentation, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def classify_image_error(error: Exception) -> ImageErrorKind:
    """Classify common provider errors without leaking their response body."""
    message = str(error).lower()
    if any(token in message for token in ("quota", "rate limit", "resource exhausted", "429")):
        return ImageErrorKind.QUOTA
    if any(token in message for token in ("api key", "unauthorized", "forbidden", "401", "403")):
        return ImageErrorKind.AUTHENTICATION
    if any(token in message for token in ("model", "configuration", "invalid request", "400")):
        return ImageErrorKind.CONFIGURATION
    if any(token in message for token in ("timeout", "timed out")):
        return ImageErrorKind.TIMEOUT
    if any(token in message for token in ("network", "connection", "dns")):
        return ImageErrorKind.NETWORK
    return ImageErrorKind.PROVIDER


def _safe_error_message(error: Exception) -> str:
    """Publish a bounded diagnostic without exposing provider credentials."""
    return str(error).replace("\n", " ")[:240]