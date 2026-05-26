"""Generate a beautiful menu PDF for sharing with guests (no ingredients/grams)."""
from datetime import datetime
from html import escape

from app.models import Event


def _format_date(dt: datetime | None) -> str:
    if not dt:
        return ""
    months = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    return f"{dt.day} {months[dt.month - 1]} {dt.year}"


def _format_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.strftime("%H:%M")


def render_menu_pdf(event: Event) -> bytes:
    """Render a beautiful printable menu (recipe titles only — no ingredients)."""
    recipes_html = ""
    for er in sorted(event.event_recipes, key=lambda x: x.recipe.title):
        title = escape(er.recipe.title)
        time = er.recipe.cook_time_min
        time_html = f'<span class="time">{time} мин</span>' if time else ""
        recipes_html += f"""
        <div class="dish">
            <div class="dot"></div>
            <div class="dish-info">
                <h3>{title}</h3>
                {time_html}
            </div>
        </div>"""

    date_str = _format_date(event.date)
    time_str = _format_time(event.date)
    title = escape(event.title)
    guests = event.guests_count

    html = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<style>
@page {{
    size: A4;
    margin: 2.5cm 2cm;
}}
* {{ box-sizing: border-box; }}
body {{
    font-family: "DejaVu Sans", "Helvetica", sans-serif;
    color: #2c2c2c;
    background: #fafaf7;
    margin: 0;
    padding: 0;
}}
.cover {{
    text-align: center;
    padding: 60px 20px 40px;
    border-bottom: 2px solid #d4b896;
}}
.cover .label {{
    font-size: 14px;
    letter-spacing: 6px;
    text-transform: uppercase;
    color: #b8956c;
    margin-bottom: 18px;
}}
.cover h1 {{
    font-size: 42px;
    font-weight: 300;
    margin: 0 0 24px;
    color: #2c2c2c;
    letter-spacing: -0.5px;
}}
.cover .meta {{
    font-size: 16px;
    color: #6c6c6c;
    margin-top: 24px;
    line-height: 1.8;
}}
.cover .meta span {{
    display: inline-block;
    margin: 0 12px;
}}
.menu {{
    padding: 50px 20px;
}}
.menu-label {{
    text-align: center;
    font-size: 14px;
    letter-spacing: 8px;
    text-transform: uppercase;
    color: #b8956c;
    margin-bottom: 40px;
}}
.dishes {{
    max-width: 500px;
    margin: 0 auto;
}}
.dish {{
    display: flex;
    align-items: center;
    padding: 18px 0;
    border-bottom: 1px solid #e8e0d4;
    gap: 18px;
}}
.dish:last-child {{
    border-bottom: none;
}}
.dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #d4b896;
    flex-shrink: 0;
}}
.dish-info {{
    flex: 1;
}}
.dish h3 {{
    font-size: 22px;
    font-weight: 400;
    margin: 0;
    color: #2c2c2c;
}}
.time {{
    display: inline-block;
    font-size: 12px;
    color: #999;
    margin-top: 4px;
    letter-spacing: 1px;
}}
.footer {{
    text-align: center;
    padding: 30px 20px;
    font-size: 11px;
    color: #b0b0b0;
    border-top: 1px solid #e8e0d4;
    letter-spacing: 2px;
    text-transform: uppercase;
}}
</style>
</head>
<body>
    <div class="cover">
        <div class="label">Меню</div>
        <h1>{title}</h1>
        <div class="meta">
            {f'<span>📅 {date_str}</span>' if date_str else ''}
            {f'<span>🕐 {time_str}</span>' if time_str else ''}
            <span>👥 {guests} {'гость' if guests == 1 else 'гостей'}</span>
        </div>
    </div>

    <div class="menu">
        <div class="menu-label">Что готовим</div>
        <div class="dishes">
            {recipes_html if recipes_html else '<p style="text-align:center;color:#999">Рецепты ещё не добавлены</p>'}
        </div>
    </div>

    <div class="footer">ПОЛЯНА · cook.coiqa.ru</div>
</body>
</html>"""

    # Lazy import: weasyprint requires native libs (pango/cairo) only available in Docker
    from weasyprint import HTML
    return HTML(string=html).write_pdf()
