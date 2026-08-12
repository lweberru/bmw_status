"""Internal Gemini and OpenAI image generation adapters."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client


@dataclass(frozen=True, slots=True)
class ImageProviderConfig:
    """Configured provider parameters held only in config-entry options."""

    provider: str
    api_key: str
    model: str
    size: str = "1024x1024"


async def async_generate_state_render(
    hass: HomeAssistant,
    config: ImageProviderConfig,
    prompt: str,
) -> bytes:
    """Generate a complete state-render image without external integrations."""
    if config.provider == "openai":
        return await _async_generate_openai(hass, config, prompt)
    if config.provider == "gemini":
        return await _async_generate_gemini(hass, config, prompt)
    raise ValueError("Unsupported image provider")


async def _async_generate_openai(
    hass: HomeAssistant,
    config: ImageProviderConfig,
    prompt: str,
) -> bytes:
    session = aiohttp_client.async_get_clientsession(hass)
    payload = {
        "model": config.model or "gpt-image-1",
        "prompt": prompt,
        "size": config.size,
        "response_format": "b64_json",
    }
    async with session.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {config.api_key}"},
        json=payload,
    ) as response:
        if response.status >= 400:
            raise RuntimeError(f"OpenAI image generation failed: {response.status} {await response.text()}")
        data = await response.json()
    image_data = ((data.get("data") or [{}])[0]).get("b64_json")
    if not image_data:
        raise RuntimeError("OpenAI image response did not contain image data")
    return base64.b64decode(image_data)


async def _async_generate_gemini(
    hass: HomeAssistant,
    config: ImageProviderConfig,
    prompt: str,
) -> bytes:
    session = aiohttp_client.async_get_clientsession(hass)
    model = config.model or "gemini-2.5-flash-image"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={config.api_key}"
    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    async with session.post(url, json=payload) as response:
        if response.status >= 400:
            raise RuntimeError(f"Gemini image generation failed: {response.status} {await response.text()}")
        data = await response.json()
    for candidate in data.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            image_data = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
            if image_data:
                return base64.b64decode(image_data)
    raise RuntimeError("Gemini image response did not contain image data")