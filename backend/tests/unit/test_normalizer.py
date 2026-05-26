"""Ingredient normalizer — unit conversion to grams.
These are pure unit tests (no DB, no LLM)."""
import pytest

from app.services import normalizer


class TestMetricWeight:
    """Russian metric units → grams."""

    @pytest.mark.parametrize("qty,unit,expected", [
        (500, "г", 500),
        (500, "гр", 500),
        (500, "грамм", 500),
        (2.5, "кг", 2500),
        (1, "килограмм", 1000),
        (200, "мг", 0.2),
    ])
    async def test_metric_weight_units(self, qty, unit, expected):
        result = await normalizer.normalize_ingredient("ingredient", qty, unit)
        assert result == pytest.approx(expected, rel=0.01)


class TestImperialWeight:
    """Imperial weight units → grams (bug fix from production)."""

    @pytest.mark.parametrize("qty,unit,expected_grams", [
        (1, "lb", 453.592),
        (2, "lb", 907.184),
        (2, "lbs", 907.184),
        (1, "pound", 453.592),
        (3, "pounds", 1360.776),
        (1, "фунт", 453.592),
        (2, "фунта", 907.184),
        (8, "oz", 226.796),
        (1, "ounce", 28.3495),
        (4, "ounces", 113.398),
    ])
    async def test_imperial_weight_converted_to_grams(self, qty, unit, expected_grams):
        result = await normalizer.normalize_ingredient("ground beef", qty, unit)
        assert result == pytest.approx(expected_grams, rel=0.01)


class TestVolumeWithKnownProduct:
    """Volume × density of a known product = grams."""

    async def test_flour_one_cup_is_about_150g(self):
        # cup = 240 ml, мука density = 0.60 g/ml → 144 g
        result = await normalizer.normalize_ingredient("мука", 1, "cup")
        assert result == pytest.approx(144, rel=0.05)

    async def test_water_one_liter_is_1000g(self):
        result = await normalizer.normalize_ingredient("вода", 1, "л")
        assert result == pytest.approx(1000, rel=0.01)

    async def test_milk_glass_uses_density(self):
        # стакан = 250 ml, молоко density = 1.03 → ~257 g
        result = await normalizer.normalize_ingredient("молоко", 1, "стакан")
        assert result == pytest.approx(257, rel=0.05)

    async def test_butter_tablespoon(self):
        # ст.л = 15 ml, масло сливочное 0.91 → ~13.6 g
        result = await normalizer.normalize_ingredient("масло сливочное", 1, "ст.л")
        assert result == pytest.approx(13.6, rel=0.1)


class TestAliasMatching:
    """Product name aliasing — different names that map to same density entry."""

    async def test_butter_alias_resolves(self):
        # 'сливочное масло' is in aliases of 'масло сливочное'
        result = await normalizer.normalize_ingredient("сливочное масло", 100, "г")
        assert result == 100  # direct weight, alias irrelevant here

    async def test_volume_alias_uses_canonical_density(self):
        # Volume conversion should work for an alias too
        a = await normalizer.normalize_ingredient("мука пшеничная", 1, "ст.л")
        b = await normalizer.normalize_ingredient("мука", 1, "ст.л")
        # Both should resolve via alias → same density
        assert a == pytest.approx(b, rel=0.01)


class TestEdgeCases:
    async def test_none_quantity_returns_none(self):
        assert await normalizer.normalize_ingredient("соль", None, "по вкусу") is None

    async def test_zero_quantity(self):
        result = await normalizer.normalize_ingredient("мука", 0, "г")
        assert result == 0

    async def test_unknown_unit_with_known_product_falls_back_to_llm(self, mocker):
        """When unit isn't recognized at all, normalizer asks LLM."""
        mock_llm = mocker.patch("app.services.normalizer.llm.fast_json", return_value={"grams": 42.0})
        result = await normalizer.normalize_ingredient("курица", 1, "тушка")
        assert result == 42.0
        mock_llm.assert_called_once()

    async def test_piece_unit_asks_llm(self, mocker):
        """шт/piece can't be converted without LLM knowing avg weight."""
        mock_llm = mocker.patch("app.services.normalizer.llm.fast_json", return_value={"grams": 150.0})
        result = await normalizer.normalize_ingredient("луковица", 2, "шт")
        assert result == 150.0

    async def test_unknown_product_asks_llm_for_density_and_caches(self, mocker, tmp_path, monkeypatch):
        """Unknown product → LLM gives density → density saved to file for reuse."""
        # Use a temporary densities file so we don't pollute the real one
        fake_file = tmp_path / "densities.json"
        fake_file.write_text('{"_comment": "test"}', encoding="utf-8")
        monkeypatch.setattr(normalizer, "_DENSITIES_PATH", fake_file)

        mock_llm = mocker.patch("app.services.normalizer.llm.fast_json", return_value={"g_per_ml": 0.5})
        result = await normalizer.normalize_ingredient("ёж", 1, "л")
        assert result == pytest.approx(500, rel=0.01)
        # Density should be cached now
        import json
        cached = json.loads(fake_file.read_text(encoding="utf-8"))
        assert "ёж" in cached
        assert cached["ёж"]["g_per_ml"] == 0.5
