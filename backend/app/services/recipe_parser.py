import httpx
from recipe_scrapers import scrape_html, scrape_me

from app.services import llm


async def parse_recipe(url: str) -> dict:
    """Return a dict with keys: title, servings, cook_time, prep_time, instructions, ingredients."""
    # --- 1. Try recipe-scrapers ---
    try:
        scraper = scrape_me(url, wild_mode=True)
        ingredients_raw = scraper.ingredients()
        instructions_raw = scraper.instructions_list() or [scraper.instructions()]
        return {
            "title": scraper.title() or "Без названия",
            "source_url": url,
            "base_servings": _int(scraper.yields()) or 4,
            "cook_time_min": scraper.total_time() or None,
            "prep_time_min": scraper.prep_time() or None,
            "instructions": [s for s in instructions_raw if s],
            "ingredients_raw": ingredients_raw,
        }
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

HTML:
{html_trimmed}"""

    data = await llm.smart_json(prompt)
    return {
        "title": data.get("title", "Без названия"),
        "source_url": url,
        "base_servings": int(data.get("servings") or 4),
        "cook_time_min": data.get("cook_time_min"),
        "prep_time_min": data.get("prep_time_min"),
        "instructions": data.get("instructions", []),
        "ingredients_raw": [
            f"{i.get('quantity', '')} {i.get('unit', '')} {i.get('name', '')}".strip()
            for i in data.get("ingredients", [])
        ],
        "ingredients_structured": data.get("ingredients", []),
    }


def _int(value) -> int | None:
    try:
        # yields() returns e.g. "4 servings"
        return int(str(value).split()[0])
    except Exception:
        return None


async def parse_recipe_from_text(text: str, title_hint: str | None = None) -> dict:
    """Parse a recipe from raw text (no URL fetching) via LLM."""
    prompt = f"""Extract recipe data from this text. Return JSON with exactly these fields:
{{
  "title": "string (use the user-provided title if given)",
  "servings": number (default 4 if unclear),
  "cook_time_min": number or null,
  "prep_time_min": number or null,
  "instructions": ["step1", "step2", ...],
  "ingredients": [{{"name": "string", "quantity": number or null, "unit": "string or null"}}]
}}

Title hint (if provided): {title_hint or "—"}

Recipe text:
{text}"""

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
