"""Convert ingredient quantities to grams using densities.json + LLM fallback."""
import json
from pathlib import Path

from app.services import llm

_DENSITIES_PATH = Path(__file__).parent.parent / "data" / "densities.json"

# Volume units → ml multipliers
_UNIT_TO_ML: dict[str, float] = {
    "мл": 1, "ml": 1, "миллилитр": 1,
    "л": 1000, "литр": 1000, "liter": 1000,
    "стакан": 250, "чашка": 250, "cup": 240,  # 1 US cup = 240 ml
    "столовая ложка": 15, "ст.л": 15, "ст. л": 15, "tbsp": 15,
    "чайная ложка": 5, "ч.л": 5, "ч. л": 5, "tsp": 5,
    "десертная ложка": 10,
    # Imperial / US volume
    "fl oz": 29.5735, "fluid ounce": 29.5735, "fluid ounces": 29.5735,
    "pint": 473.176, "pt": 473.176, "pints": 473.176,
    "quart": 946.353, "qt": 946.353, "quarts": 946.353,
    "gallon": 3785.41, "gal": 3785.41, "gallons": 3785.41,
}

# Weight units → grams multipliers
_UNIT_TO_G: dict[str, float] = {
    "г": 1, "гр": 1, "грамм": 1, "граммов": 1, "грамма": 1, "gram": 1, "grams": 1, "g": 1,
    "кг": 1000, "килограмм": 1000, "килограммов": 1000, "kg": 1000,
    "мг": 0.001, "mg": 0.001,
    # Imperial / US weight
    "фунт": 453.592, "фунта": 453.592, "фунтов": 453.592,
    "lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592,
    "унция": 28.3495, "унц": 28.3495, "унции": 28.3495, "унций": 28.3495,
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
}


def _load() -> dict:
    with open(_DENSITIES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(_DENSITIES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _find_product(name: str, densities: dict) -> dict | None:
    name_lower = name.lower().strip()
    # exact key match
    if name_lower in densities:
        return densities[name_lower]
    # alias match
    for key, entry in densities.items():
        if key.startswith("_"):
            continue
        for alias in entry.get("aliases", []):
            if alias.lower() == name_lower:
                return entry
    # partial match (name contains key or key contains name)
    for key, entry in densities.items():
        if key.startswith("_"):
            continue
        if key in name_lower or name_lower in key:
            return entry
    return None


async def normalize_ingredient(name: str, quantity: float | None, unit: str | None) -> float | None:
    """Return weight in grams, or None if cannot determine."""
    if quantity is None:
        return None

    unit_clean = (unit or "").lower().strip().rstrip(".")

    # --- Direct weight unit ---
    for u, factor in _UNIT_TO_G.items():
        if unit_clean == u or unit_clean.startswith(u):
            return quantity * factor

    # --- штука / piece — can't normalize without product context ---
    if unit_clean in ("шт", "штука", "штук", "piece", "pc", ""):
        # Try to get grams-per-piece from LLM
        return await _llm_normalize(name, quantity, unit or "шт")

    # --- Volume unit ---
    ml_factor = None
    for u, factor in _UNIT_TO_ML.items():
        if unit_clean == u or unit_clean.startswith(u):
            ml_factor = factor
            break

    if ml_factor is None:
        # Unknown unit — ask LLM
        return await _llm_normalize(name, quantity, unit or "")

    ml_total = quantity * ml_factor
    densities = _load()
    entry = _find_product(name, densities)

    if entry:
        return ml_total * entry["g_per_ml"]

    # Product not in densities — ask LLM, cache result
    g_per_ml = await _llm_density(name)
    if g_per_ml:
        densities = _load()
        densities[name.lower()] = {"g_per_ml": g_per_ml, "aliases": []}
        _save(densities)
        return ml_total * g_per_ml

    return None


async def _llm_density(name: str) -> float | None:
    prompt = f'What is the density of "{name}" in grams per milliliter? Return JSON: {{"g_per_ml": number}}'
    try:
        result = await llm.fast_json(prompt)
        return float(result["g_per_ml"])
    except Exception:
        return None


async def _llm_normalize(name: str, quantity: float, unit: str) -> float | None:
    prompt = (
        f'Convert "{quantity} {unit}" of "{name}" to grams. '
        f'Return JSON: {{"grams": number}} or {{"grams": null}} if impossible.'
    )
    try:
        result = await llm.fast_json(prompt)
        val = result.get("grams")
        return float(val) if val is not None else None
    except Exception:
        return None
