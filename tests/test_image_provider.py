"""Check the image provider's HTTP contract without paid API requests."""

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.bmw_status.image_provider import (
    ImageProviderConfig,
    async_generate_state_render,
)


@pytest.mark.parametrize("model", ["", "gpt-image-1.5"])
async def test_openai_generates_png_without_legacy_response_format(monkeypatch, model):
    """GPT Image requests decode the result and use supported, economical options."""
    image = b"\x89PNG\r\n\x1a\nexample"
    response = MagicMock(status=200)
    response.json = AsyncMock(return_value={"data": [{"b64_json": base64.b64encode(image).decode()}]})
    session = MagicMock()
    session.post.return_value.__aenter__.return_value = response
    monkeypatch.setattr(
        "custom_components.bmw_status.image_provider.aiohttp_client.async_get_clientsession",
        lambda hass: session,
    )

    result = await async_generate_state_render(
        None, ImageProviderConfig("openai", "test-key", model), "A parked BMW"
    )

    assert result == image
    session.post.assert_called_once_with(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": "Bearer test-key"},
        json={
            "model": model or "gpt-image-2.5-flare",
            "prompt": "A parked BMW",
            "size": "1024x1024",
            "output_format": "png",
            "quality": "low",
            "n": 1,
        },
    )
