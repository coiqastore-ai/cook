"""Recipe parser — URL, text, image, audio (with LLM mocked)."""
import pytest

from app.services import recipe_parser


class TestParseRecipeFromText:
    async def test_parses_well_formed_text(self, mocker):
        mocker.patch.object(recipe_parser.llm, "smart_json", return_value={
            "title": "Шарлотка",
            "servings": 6,
            "cook_time_min": 40,
            "prep_time_min": 10,
            "instructions": ["шаг 1", "шаг 2"],
            "ingredients": [
                {"name": "мука", "quantity": 200, "unit": "г"},
                {"name": "яйца", "quantity": 4, "unit": "шт"},
            ],
        })
        result = await recipe_parser.parse_recipe_from_text("текст рецепта", title_hint=None)
        assert result["title"] == "Шарлотка"
        assert result["base_servings"] == 6
        assert len(result["ingredients_structured"]) == 2

    async def test_title_hint_used_when_llm_returns_empty_title(self, mocker):
        mocker.patch.object(recipe_parser.llm, "smart_json", return_value={
            "title": None,
            "servings": 4,
            "instructions": [],
            "ingredients": [{"name": "X", "quantity": 1, "unit": "шт"}],
        })
        result = await recipe_parser.parse_recipe_from_text("...", title_hint="Тестовое блюдо")
        assert result["title"] == "Тестовое блюдо"

    async def test_pinterest_noise_is_stripped_before_llm(self, mocker):
        """Pinterest preview block at the end of pasted text must be cleaned out."""
        captured = {}

        async def capture(prompt):
            captured["prompt"] = prompt
            return {"title": "X", "servings": 4, "instructions": [], "ingredients": [{"name": "a", "quantity": 1}]}

        mocker.patch.object(recipe_parser.llm, "smart_json", side_effect=capture)
        await recipe_parser.parse_recipe_from_text(
            "Список ингредиентов:\n200г муки\n\nPinterest\nВзгляните на этот пин от Coiqa\nMeet your new...",
        )
        # Pinterest block should not appear in the prompt sent to LLM
        assert "Pinterest" not in captured["prompt"]
        assert "Взгляните на этот пин" not in captured["prompt"]


class TestParseRecipeFromUrl_RejectsJunk:
    """The most important security/quality guard: don't save empty recipes."""

    async def test_empty_title_raises(self, mocker):
        # Force the recipe-scrapers path to fail so we hit the LLM fallback
        mocker.patch.object(recipe_parser, "scrape_me", side_effect=Exception("not supported"))
        # Mock the HTTP fetch
        import httpx
        mock_resp = mocker.AsyncMock()
        mock_resp.text = "<html><body>empty</body></html>"
        mock_resp.raise_for_status = mocker.Mock()
        mocker.patch("httpx.AsyncClient.get", return_value=mock_resp)
        # Mock LLM returning empty title (Дзен-like response)
        mocker.patch.object(recipe_parser.llm, "smart_json", return_value={
            "title": "Название не найдено",
            "ingredients": [],
        })
        with pytest.raises(ValueError, match=r"не нашлось рецепта|защищён JS"):
            await recipe_parser.parse_recipe("https://dzen.ru/example")

    async def test_too_few_ingredients_raises(self, mocker):
        mocker.patch.object(recipe_parser, "scrape_me", side_effect=Exception("nope"))
        import httpx
        mock_resp = mocker.AsyncMock()
        mock_resp.text = "<html></html>"
        mock_resp.raise_for_status = mocker.Mock()
        mocker.patch("httpx.AsyncClient.get", return_value=mock_resp)
        mocker.patch.object(recipe_parser.llm, "smart_json", return_value={
            "title": "Кулинарный шедевр",
            "ingredients": [{"name": "вода", "quantity": 1, "unit": "л"}],  # only 1 ingredient
        })
        with pytest.raises(ValueError, match=r"не получилось извлечь ингредиенты"):
            await recipe_parser.parse_recipe("https://example.com/foo")


class TestParseRecipeFromAudio:
    async def test_audio_parser_returns_recipe_dict(self, mocker):
        mocker.patch.object(recipe_parser.llm, "audio_json", return_value={
            "title": "Шарлотка из голоса",
            "servings": 4,
            "instructions": ["шаг 1"],
            "ingredients": [{"name": "мука", "quantity": 200, "unit": "г"}],
        })
        result = await recipe_parser.parse_recipe_from_audio("fakebase64", audio_format="ogg")
        assert result["title"] == "Шарлотка из голоса"
        assert result["source_url"] is None  # voice has no source URL


class TestLooksRussian:
    def test_cyrillic_text_recognized(self):
        assert recipe_parser._looks_russian("Шарлотка с яблоками")

    def test_english_text_not_russian(self):
        assert not recipe_parser._looks_russian("Apple pie with cinnamon")

    def test_empty_string_treated_as_russian(self):
        # Empty title shouldn't trigger translation
        assert recipe_parser._looks_russian("")

    def test_mixed_with_majority_cyrillic(self):
        assert recipe_parser._looks_russian("Salad оливье 200 г")

    def test_mixed_with_majority_english(self):
        assert not recipe_parser._looks_russian("Layered Tortilla Kebab Skewers (мясо)")


class TestPinterestNoiseClean:
    def test_strips_pinterest_preview_block(self):
        text = "Recipe content\n\nPinterest\nВзгляните на этот пин\nMeet your new..."
        cleaned = recipe_parser._clean_pinterest_noise(text)
        assert "Pinterest" not in cleaned
        assert "Взгляните" not in cleaned
        assert "Recipe content" in cleaned

    def test_preserves_normal_text(self):
        text = "Шарлотка\n\n200г муки\n4 яйца"
        cleaned = recipe_parser._clean_pinterest_noise(text)
        assert cleaned == text
