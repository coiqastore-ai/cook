import json

from openai import AsyncOpenAI

from app.config import settings

_client: AsyncOpenAI | None = None

_JSON_SYSTEM = "You are a helpful assistant. Always respond with valid JSON only, no markdown fences."


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
        )
    return _client


async def _chat(model: str, prompt: str, system: str) -> str:
    response = await get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return response.choices[0].message.content or ""


def _parse_json(raw: str) -> dict | list:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


# --- Public helpers ---

async def fast(prompt: str) -> str:
    """DeepSeek — cheap tasks: normalization, name grouping."""
    return await _chat(settings.openrouter_model_fast, prompt, _JSON_SYSTEM)


async def smart(prompt: str) -> str:
    """Gemini 2.5 Flash — complex tasks: recipe parsing, timeline."""
    return await _chat(settings.openrouter_model_smart, prompt, _JSON_SYSTEM)


async def fast_json(prompt: str) -> dict | list:
    return _parse_json(await fast(prompt))


async def smart_json(prompt: str) -> dict | list:
    return _parse_json(await smart(prompt))


def _as_data_url(image_b64: str) -> str:
    return image_b64 if image_b64.startswith("data:") else f"data:image/jpeg;base64,{image_b64}"


async def vision_multi(prompt: str, images_b64: list[str]) -> str:
    """Qwen 2.5 VL — recognize text from one OR MULTIPLE images at once.
    Pass several images when they're parts of the same recipe (album in Telegram)."""
    if not images_b64:
        raise ValueError("vision_multi needs at least one image")
    content: list[dict] = [{"type": "text", "text": prompt}]
    for img in images_b64:
        content.append({"type": "image_url", "image_url": {"url": _as_data_url(img)}})
    response = await get_client().chat.completions.create(
        model=settings.openrouter_model_vision,
        messages=[{"role": "user", "content": content}],
        temperature=0,
    )
    return response.choices[0].message.content or ""


async def vision_multi_json(prompt: str, images_b64: list[str]) -> dict | list:
    return _parse_json(await vision_multi(prompt, images_b64))


# Single-image helpers — kept as thin wrappers for callers that still use them
async def vision(prompt: str, image_b64: str) -> str:
    return await vision_multi(prompt, [image_b64])


async def vision_json(prompt: str, image_b64: str) -> dict | list:
    return _parse_json(await vision(prompt, image_b64))


# Backward-compat alias
async def chat_json(prompt: str) -> dict | list:
    return await fast_json(prompt)


# --- Audio input through OpenRouter (Gemini 2.5 Flash supports audio) ---

async def audio_chat(prompt: str, audio_b64: str, audio_format: str = "ogg") -> str:
    """Send an audio clip + text prompt to Gemini via OpenRouter, return its reply.
    Gemini accepts: ogg, wav, mp3, aiff, aac, flac. Telegram voice is ogg/opus — works."""
    response = await get_client().chat.completions.create(
        model=settings.openrouter_model_smart,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "input_audio", "input_audio": {"data": audio_b64, "format": audio_format}},
            ],
        }],
        temperature=0,
    )
    return response.choices[0].message.content or ""


async def audio_json(prompt: str, audio_b64: str, audio_format: str = "ogg") -> dict | list:
    return _parse_json(await audio_chat(prompt, audio_b64, audio_format))
