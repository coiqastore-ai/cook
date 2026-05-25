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


# Backward-compat alias used by calendar_sync (no LLM needed there, but keep import clean)
async def chat_json(prompt: str) -> dict | list:
    return await fast_json(prompt)
