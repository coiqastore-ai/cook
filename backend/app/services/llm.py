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


async def vision(prompt: str, image_b64: str) -> str:
    """Qwen 2.5 VL — recognize text from images (photo, screenshot).
    image_b64 can be either a raw base64 string or full data URL.
    """
    if not image_b64.startswith("data:"):
        image_b64 = f"data:image/jpeg;base64,{image_b64}"
    response = await get_client().chat.completions.create(
        model=settings.openrouter_model_vision,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_b64}},
                ],
            }
        ],
        temperature=0,
    )
    return response.choices[0].message.content or ""


async def vision_json(prompt: str, image_b64: str) -> dict | list:
    return _parse_json(await vision(prompt, image_b64))


# Backward-compat alias
async def chat_json(prompt: str) -> dict | list:
    return await fast_json(prompt)
