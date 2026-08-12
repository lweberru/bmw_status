"""Tests for deterministic BMW Status image job helpers."""

from custom_components.bmw_status.image_jobs import (
    ImageErrorKind,
    ImageJobManager,
    ImageJobState,
    classify_image_error,
    presentation_key,
)


def test_presentation_key_is_stable_for_equivalent_mapping_order():
    """Equivalent semantic presentations reuse the same cache key."""
    first = {"status": {"key": "parked"}, "vehicle": {"name": "Test BMW"}}
    second = {"vehicle": {"name": "Test BMW"}, "status": {"key": "parked"}}

    assert presentation_key(first) == presentation_key(second)
    assert len(presentation_key(first)) == 24


def test_classify_image_error_uses_safe_retry_categories():
    """Provider text selects the retry and blocking policy category."""
    assert classify_image_error(RuntimeError("HTTP 429 quota exceeded")) is ImageErrorKind.QUOTA
    assert classify_image_error(RuntimeError("network connection failed")) is ImageErrorKind.NETWORK
    assert classify_image_error(RuntimeError("invalid API key")) is ImageErrorKind.AUTHENTICATION
    assert classify_image_error(RuntimeError("request timed out")) is ImageErrorKind.TIMEOUT


async def test_image_job_quota_blocks_further_requests(hass):
    """A quota error prevents a second provider request until its retry deadline."""
    published: list[ImageJobState] = []

    async def render(_state_key: str) -> None:
        raise RuntimeError("HTTP 429 quota exceeded")

    manager = ImageJobManager(hass, render, published.append)

    manager.async_request("first")
    manager.async_shutdown()
    await manager._async_start(None)
    manager.async_request("second")

    assert published[-2].status == "error"
    assert published[-2].retry_after is not None
    assert published[-1] == ImageJobState(
        "error",
        "Bildgenerierung wartet auf Provider-Kontingent.",
        published[-2].retry_after,
    )


async def test_image_job_network_failure_schedules_retry(hass):
    """A temporary network failure is retried after the configured first delay."""
    published: list[ImageJobState] = []

    async def render(_state_key: str) -> None:
        raise RuntimeError("network connection failed")

    manager = ImageJobManager(hass, render, published.append)

    manager.async_request("state")
    manager.async_shutdown()
    await manager._async_start(None)

    assert manager._retry_attempts == {"state": 1}
    assert manager._pending_key == "state"
    assert manager._scheduled_cancel is not None
    assert published[-1].status == "error"
    manager.async_shutdown()