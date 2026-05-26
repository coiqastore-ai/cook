"""Generate share-card cover PNG for Telegram link preview (og:image)."""
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.models import Event

_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

W, H = 1200, 630  # Telegram's preferred og:image size


def _gradient_bg(draw: ImageDraw.ImageDraw):
    # Subtle warm gradient: top #fafaf7 → bottom #f0e2c8
    for y in range(H):
        r = int(0xfa + (0xf0 - 0xfa) * y / H)
        g = int(0xfa + (0xe2 - 0xfa) * y / H)
        b = int(0xf7 + (0xc8 - 0xf7) * y / H)
        draw.line([(0, y), (W, y)], fill=(r, g, b))


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def render_cover_png(event: Event) -> bytes:
    img = Image.new("RGB", (W, H), color="#fafaf7")
    draw = ImageDraw.Draw(img)
    _gradient_bg(draw)

    # Top decorative line
    draw.rectangle([(80, 90), (W - 80, 92)], fill="#d4b896")

    # Brand label
    f_brand = ImageFont.truetype(_FONT_BOLD, 30)
    draw.text((W // 2, 65), "ПОЛЯНА · МЕНЮ", fill="#b8956c", font=f_brand, anchor="mm")

    # Event title
    title = _truncate(event.title, 36)
    f_title = ImageFont.truetype(_FONT_BOLD, 78)
    draw.text((W // 2, 180), title, fill="#2c2c2c", font=f_title, anchor="mm")

    # Date / guests / dish count
    parts: list[str] = []
    if event.date:
        parts.append(event.date.strftime("%d.%m.%Y"))
        if event.date.strftime("%H:%M") != "00:00":
            parts[-1] += "  " + event.date.strftime("%H:%M")
    parts.append(f"{event.guests_count} гостей")
    n_dishes = len(event.event_recipes)
    parts.append(f"{n_dishes} {'блюдо' if n_dishes == 1 else ('блюда' if n_dishes < 5 else 'блюд')}")
    f_meta = ImageFont.truetype(_FONT_REG, 30)
    draw.text((W // 2, 260), "  ·  ".join(parts), fill="#6c6c6c", font=f_meta, anchor="mm")

    # Recipe titles (up to 5)
    f_dish = ImageFont.truetype(_FONT_REG, 30)
    f_dish_bold = ImageFont.truetype(_FONT_BOLD, 30)
    sorted_recipes = sorted(event.event_recipes, key=lambda er: er.recipe.title)
    visible = sorted_recipes[:5]
    y_start = 360
    for i, er in enumerate(visible):
        line = _truncate("• " + er.recipe.title, 38)
        draw.text((W // 2, y_start + i * 48), line, fill="#2c2c2c", font=f_dish, anchor="mm")
    if len(sorted_recipes) > 5:
        more = len(sorted_recipes) - 5
        draw.text(
            (W // 2, y_start + 5 * 48),
            f"и ещё {more} {'блюдо' if more == 1 else ('блюда' if more < 5 else 'блюд')}…",
            fill="#999",
            font=f_dish,
            anchor="mm",
        )

    # Footer CTA
    f_cta = ImageFont.truetype(_FONT_BOLD, 24)
    draw.text((W // 2, H - 45), "ОТКРЫТЬ В ПОЛЯНЕ →", fill="#b8956c", font=f_cta, anchor="mm")

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
