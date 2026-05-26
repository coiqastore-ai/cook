import json

import httpx
from recipe_scrapers import scrape_html, scrape_me

from app.services import llm


def _looks_russian(text: str) -> bool:
    """Heuristic: more than 30% Cyrillic letters → consider it Russian."""
    if not text:
        return True
    cyrillic = sum(1 for c in text if "а" <= c.lower() <= "я" or c.lower() == "ё")
    letters = sum(1 for c in text if c.isalpha())
    return letters == 0 or cyrillic / letters > 0.3


async def _translate_recipe_to_russian(data: dict) -> dict:
    """Translate recipe-scrapers result to Russian if it's not already."""
    title = data.get("title") or ""
    raw_ingredients = " ".join(data.get("ingredients_raw") or [])
    if _looks_russian(title) and _looks_russian(raw_ingredients):
        return data

    payload = {
        "title": data.get("title", ""),
        "instructions": data.get("instructions", []),
        "ingredients_raw": data.get("ingredients_raw", []),
    }
    prompt = f"""Translate this recipe data from any language to RUSSIAN. Return the same JSON structure with all text translated.
Keep ingredient quantities/numbers intact within the strings.

{json.dumps(payload, ensure_ascii=False)}"""
    try:
        translated = await llm.smart_json(prompt)
        if isinstance(translated, dict):
            data["title"] = translated.get("title") or data["title"]
            data["instructions"] = translated.get("instructions") or data["instructions"]
            data["ingredients_raw"] = translated.get("ingredients_raw") or data["ingredients_raw"]
    except Exception:
        pass  # if translation fails, return original
    return data


async def parse_recipe(url: str) -> dict:
    """Return a dict with keys: title, servings, cook_time, prep_time, instructions, ingredients."""
    # --- 1. Try recipe-scrapers ---
    try:
        scraper = scrape_me(url, wild_mode=True)
        ingredients_raw = scraper.ingredients()
        instructions_raw = scraper.instructions_list() or [scraper.instructions()]
        data = {
            "title": scraper.title() or "Без названия",
            "source_url": url,
            "base_servings": _int(scraper.yields()) or 4,
            "cook_time_min": scraper.total_time() or None,
            "prep_time_min": scraper.prep_time() or None,
            "instructions": [s for s in instructions_raw if s],
            "ingredients_raw": ingredients_raw,
        }
        # Translate if the source was in another language
        return await _translate_recipe_to_russian(data)
    except Exception:
        pass

    # --- 2. Fallback: fetch HTML → LLM ---
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        html = resp.text

    # Trim HTML to avoid huge context — keep first 30k chars
    html_trimmed = html[:30_000]

    prompt = f"""Extract recipe data from this HTML page and return JSON with exactly these fields:
{{
  "title": "string",
  "servings": number,
  "cook_time_min": number or null,
  "prep_time_min": number or null,
  "instructions": ["step1", "step2", ...],
  "ingredients": [{{"name": "string", "quantity": number or null, "unit": "string or null"}}]
}}

IMPORTANT: Always return all text in RUSSIAN. Translate the title, ingredient names, units, and instructions to Russian if the source is in another language.
CONVERT imperial units to metric: pounds/lb → kg (1 lb = 0.453 kg, round to 0.05 kg), ounces/oz → g (1 oz = 28 g, round to 5 g), fl oz → ml, cups (US) → ml (1 cup = 240 ml), pints/quarts/gallons → ml/l. Inches → cm where applicable. Fahrenheit → Celsius in cooking temperatures.

HTML:
{html_trimmed}"""

    data = await llm.smart_json(prompt)
    ingredients = data.get("ingredients") or []
    title = (data.get("title") or "").strip()

    # Guard: if LLM couldn't extract anything meaningful, don't save a junk recipe.
    # Likely a JS-rendered SPA (Дзен, Pinterest, Instagram, рекламные блоги).
    if not title or title.lower() in ("без названия", "название не найдено", "recipe title not found", "untitled"):
        raise ValueError(
            "На странице не нашлось рецепта (вероятно сайт защищён JS-рендерингом). "
            "Попробуй пришли скриншот страницы или скопируй текст рецепта."
        )
    if len(ingredients) < 2:
        raise ValueError(
            "Удалось найти заголовок, но не получилось извлечь ингредиенты. "
            "Попробуй пришли скриншот страницы или скопируй текст рецепта."
        )

    return {
        "title": title,
        "source_url": url,
        "base_servings": int(data.get("servings") or 4),
        "cook_time_min": data.get("cook_time_min"),
        "prep_time_min": data.get("prep_time_min"),
        "instructions": data.get("instructions", []),
        "ingredients_raw": [
            f"{i.get('quantity', '')} {i.get('unit', '')} {i.get('name', '')}".strip()
            for i in ingredients
        ],
        "ingredients_structured": ingredients,
    }


def _int(value) -> int | None:
    try:
        # yields() returns e.g. "4 servings"
        return int(str(value).split()[0])
    except Exception:
        return None


async def parse_recipe_from_images(images_b64: list[str], title_hint: str | None = None) -> dict:
    """Parse a SINGLE recipe from one or several photos (Telegram media group).
    The LLM treats all images as parts of the same recipe — different pages of a book,
    multiple Pinterest screenshots, etc. It should combine info, not duplicate."""
    if not images_b64:
        raise ValueError("Need at least one image")

    intro = (
        "These images all belong to ONE single recipe — likely different pages or screenshots "
        "of the same dish (e.g. an Instagram/Pinterest album). Read text from every image and "
        "COMBINE the information into ONE recipe (do NOT make a list of separate recipes; do NOT duplicate ingredients)."
        if len(images_b64) > 1
        else "Look at this image and extract the recipe. The image may be a photo of a printed recipe, a handwritten note, or a screenshot from a website/Pinterest/Instagram. Read all text carefully."
    )

    prompt = f"""{intro}

Return JSON with exactly these fields:
{{
  "title": "string",
  "servings": number (default 4 if unclear),
  "cook_time_min": number or null,
  "prep_time_min": number or null,
  "instructions": ["step1", "step2", ...],
  "ingredients": [{{"name": "string", "quantity": number or null, "unit": "string or null"}}]
}}

IMPORTANT:
- Read EVERY ingredient from EVERY image. Do not skip — even small items like salt, pepper, garlic, oil, water, ice, herbs.
- Always return all text in RUSSIAN. Translate from any language to Russian.
- CONVERT all imperial/US units to metric: lb/pounds → kg, oz/ounces → g, fl oz → ml, cup (US) → ml (1 cup = 240 ml), pint → ml, gallon → l, °F → °C, inches → cm.
- For "to taste" amounts — quantity: null, unit: "по вкусу".
- If you can't read something, omit it rather than guess."""

    data = await llm.vision_multi_json(prompt, images_b64)
    if not isinstance(data, dict):
        raise ValueError("Vision LLM returned non-object response")
    return {
        "title": data.get("title") or title_hint or "Рецепт с фото",
        "source_url": None,
        "base_servings": int(data.get("servings") or 4),
        "cook_time_min": data.get("cook_time_min"),
        "prep_time_min": data.get("prep_time_min"),
        "instructions": data.get("instructions", []),
        "ingredients_structured": data.get("ingredients", []),
    }


# Backward-compat: single-image alias
async def parse_recipe_from_image(image_b64: str, title_hint: str | None = None) -> dict:
    return await parse_recipe_from_images([image_b64], title_hint=title_hint)


async def parse_recipe_from_audio(audio_b64: str, audio_format: str = "ogg") -> dict:
    """Transcribe a voice message + extract recipe data in ONE LLM call via Gemini audio input."""
    prompt = """This audio is someone dictating a recipe. Transcribe what they say and extract recipe data.

Return JSON with exactly these fields:
{
  "title": "string (give it a sensible name from context if not explicitly named)",
  "servings": number (default 4 if unclear),
  "cook_time_min": number or null,
  "prep_time_min": number or null,
  "instructions": ["step1", "step2", ...] (if mentioned, else empty array),
  "ingredients": [{"name": "string", "quantity": number or null, "unit": "string or null"}]
}

IMPORTANT:
- Always return all text in RUSSIAN.
- CONVERT imperial units to metric (lb→kg, oz→g, cup→ml, etc.).
- Read EVERY ingredient mentioned — including small items like salt, pepper, oil.
- For amounts like 'по вкусу' / 'щепотка' — quantity: null, unit: "по вкусу".
- If quantity isn't clear, leave it null rather than guess."""

    data = await llm.audio_json(prompt, audio_b64, audio_format=audio_format)
    if not isinstance(data, dict):
        raise ValueError("Audio LLM returned non-object response")
    return {
        "title": data.get("title") or "Рецепт с голоса",
        "source_url": None,
        "base_servings": int(data.get("servings") or 4),
        "cook_time_min": data.get("cook_time_min"),
        "prep_time_min": data.get("prep_time_min"),
        "instructions": data.get("instructions", []),
        "ingredients_structured": data.get("ingredients", []),
    }


def _clean_pinterest_noise(text: str) -> str:
    """Strip obvious Pinterest/Instagram preview blocks from copied text."""
    lines = text.splitlines()
    cleaned = []
    skip_block = False
    for line in lines:
        stripped = line.strip()
        # Detect Pinterest/Instagram preview headers
        if stripped in ("Pinterest", "Instagram", "Reels", "TikTok"):
            skip_block = True
            continue
        if skip_block:
            # Skip lines that look like preview metadata until blank line ends the block
            if not stripped or stripped.startswith(("Взгляните", "Check out", "Meet your", "Posted by")):
                continue
            # exit block once we see a normal line
            skip_block = False
        cleaned.append(line)
    return "\n".join(cleaned).strip()


async def parse_recipe_from_text(text: str, title_hint: str | None = None) -> dict:
    """Parse a recipe from raw text (no URL fetching) via LLM."""
    clean_text = _clean_pinterest_noise(text)
    prompt = f"""Extract recipe data from this text. Return JSON with exactly these fields:
{{
  "title": "string (use the user-provided title if given)",
  "servings": number (default 4 if unclear),
  "cook_time_min": number or null,
  "prep_time_min": number or null,
  "instructions": ["step1", "step2", ...],
  "ingredients": [{{"name": "string", "quantity": number or null, "unit": "string or null"}}]
}}

IMPORTANT:
- Always return all text in RUSSIAN. Translate from any language to Russian.
- CONVERT all imperial/US units to metric: lb/pounds → kg, oz/ounces → g, fl oz → ml, cup (US) → ml (240 ml), pint → ml, gallon → l, °F → °C, inches → cm.
- Read EVERY ingredient — including salt, pepper, oil, water, etc. Don't skip "small" items.
- Section headers in the text (e.g. "Мясо", "Овощи", "Приправы") are categories — extract the ingredients that follow, ignore the headers themselves.
- For "to taste" → quantity: null, unit: "по вкусу".

Title hint (if provided): {title_hint or "—"}

Recipe text:
{clean_text}"""

    data = await llm.smart_json(prompt)
    return {
        "title": data.get("title") or title_hint or "Без названия",
        "source_url": None,
        "base_servings": int(data.get("servings") or 4),
        "cook_time_min": data.get("cook_time_min"),
        "prep_time_min": data.get("prep_time_min"),
        "instructions": data.get("instructions", []),
        "ingredients_structured": data.get("ingredients", []),
    }


async def parse_ingredients_text(raw_lines: list[str]) -> list[dict]:
    """Parse a list of raw ingredient strings into structured {name, quantity, unit} via LLM."""
    prompt = f"""Parse these ingredient strings into JSON array. Each element: {{"name": str, "quantity": number or null, "unit": str or null}}.
Return only the JSON array.

Ingredients:
{chr(10).join(raw_lines)}"""
    result = await llm.smart_json(prompt)
    if isinstance(result, list):
        return result
    return []
