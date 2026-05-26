"""Smoke tests for PDF and PNG renderers — they must produce valid binary output
with Cyrillic content without crashing. Skipped locally if WeasyPrint native libs missing."""
from datetime import datetime
from types import SimpleNamespace

import pytest


def _fake_event(title="Шашлыки на даче", n_recipes=3):
    """Build a duck-typed Event that has the attributes used by renderers (no DB)."""
    recipes = [
        SimpleNamespace(
            recipe=SimpleNamespace(title=f"Блюдо {i} ёжик", cook_time_min=30 + i * 10),
        )
        for i in range(n_recipes)
    ]
    return SimpleNamespace(
        id=1,
        title=title,
        date=datetime(2026, 5, 30, 18, 0),
        guests_count=10,
        notes=None,
        event_recipes=recipes,
    )


def _render_or_skip(event):
    """Call share_card.render_cover_png, skipping if DejaVu fonts aren't on this host
    (they are bundled in our Docker image but absent on dev Windows machines)."""
    from app.services.share_card import render_cover_png
    try:
        return render_cover_png(event)
    except OSError as e:
        pytest.skip(f"DejaVu fonts unavailable on this host: {e}")


class TestShareCard:
    def test_render_cover_png_returns_valid_png(self):
        png = _render_or_skip(_fake_event())
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert 5_000 < len(png) < 200_000

    def test_handles_long_cyrillic_title(self):
        long_title = "Юбилей бабушки Александры — 80 лет, грандиозное событие 🎉"
        png = _render_or_skip(_fake_event(title=long_title))
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_handles_zero_recipes(self):
        png = _render_or_skip(_fake_event(n_recipes=0))
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_handles_many_recipes(self):
        """Should still produce valid PNG when there are way more recipes than fit."""
        png = _render_or_skip(_fake_event(n_recipes=20))
        assert png[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.slow
class TestPdfMenu:
    """WeasyPrint requires native libs (pango/cairo). Skipped if not installed."""

    def test_render_menu_pdf_returns_valid_pdf(self):
        try:
            from app.services.pdf_menu import render_menu_pdf
            pdf = render_menu_pdf(_fake_event())
        except (OSError, ImportError) as e:
            pytest.skip(f"WeasyPrint native libs unavailable: {e}")
        # PDF magic number
        assert pdf[:5] == b"%PDF-"
        assert b"%%EOF" in pdf[-1024:]
