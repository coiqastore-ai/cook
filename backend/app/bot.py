"""Telegram bot — запускается отдельно: uv run python -m app.bot_runner"""
import asyncio
import base64
import logging
import os
from datetime import datetime
from io import BytesIO

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    PhotoSize,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.config import settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Button labels (single source of truth)
# ---------------------------------------------------------------------------

BTN_OPEN_APP = "📲 Открыть приложение"
BTN_NEW_EVENT = "➕ Новое событие"
BTN_IMPORT_URL = "🔗 Рецепт по ссылке"
BTN_IMPORT_TEXT = "📝 Рецепт текстом"
BTN_IMPORT_PHOTO_INFO = "📷 Рецепт с фото"
BTN_HELP = "❓ Помощь"


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_OPEN_APP, web_app=WebAppInfo(url=settings.miniapp_url))],
            [KeyboardButton(text=BTN_NEW_EVENT)],
            [KeyboardButton(text=BTN_IMPORT_URL), KeyboardButton(text=BTN_IMPORT_TEXT)],
            [KeyboardButton(text=BTN_IMPORT_PHOTO_INFO), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def open_app_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📲 Открыть приложение", web_app=WebAppInfo(url=settings.miniapp_url))
    ]])


# ---------------------------------------------------------------------------
# FSM states
# ---------------------------------------------------------------------------

class NewEvent(StatesGroup):
    title = State()
    date = State()
    guests = State()


class ImportText(StatesGroup):
    waiting_for_text = State()


class ImportUrl(StatesGroup):
    waiting_for_url = State()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def api_post(path: str, data: dict, timeout: float = 180) -> dict | None:
    """Returns parsed JSON on success, None on failure. Logs the response body for diagnostics."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.post(f"{API_BASE}{path}", json=data)
            if r.status_code >= 400:
                log.error("API POST %s → %d: %s", path, r.status_code, r.text[:500])
                return None
            return r.json()
        except Exception as e:
            log.error("API POST %s exception: %s", path, e)
            return None


# ---------------------------------------------------------------------------
# Universal handlers
# ---------------------------------------------------------------------------

async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    # Deep-link: /start event_<id> → join as collaborator
    args = message.text.split(maxsplit=1) if message.text else []
    if len(args) > 1 and args[1].startswith("event_"):
        try:
            event_id = int(args[1].removeprefix("event_"))
        except ValueError:
            event_id = None
        if event_id and message.from_user:
            user = message.from_user
            payload = {
                "telegram_user_id": user.id,
                "name": (user.full_name or user.first_name or "")[:200],
                "username": user.username,
            }
            ev = await api_post(f"/events/{event_id}/collaborators", payload)
            if ev:
                await message.answer(
                    f"✅ Ты добавлен(а) в событие *{ev['title']}*!\n\n"
                    f"Открой Mini App — там сможешь редактировать список рецептов и закупку 👇",
                    parse_mode="Markdown",
                    reply_markup=main_kb(),
                )
                return
            await message.answer("❌ Не удалось присоединиться к событию (возможно оно удалено).", reply_markup=main_kb())
            return

    await message.answer(
        "👋 Привет! Я Mealie Bot — помогаю планировать застолья.\n\n"
        "Что я умею:\n"
        "• Создавать события и хранить ваши рецепты\n"
        "• Импортировать рецепты по ссылке, тексту или с фото\n"
        "• Собирать единый список закупки по событию\n"
        "• Делать таймлайн готовки\n"
        "• Напоминать о событии за сутки\n"
        "• Совместное редактирование с друзьями\n\n"
        "Выбери действие на клавиатуре снизу 👇",
        reply_markup=main_kb(),
    )


async def show_help(message: Message):
    await message.answer(
        "📖 *Как пользоваться:*\n\n"
        "🟢 *Создать событие:* нажми «Новое событие» → введи название, дату и кол-во гостей\n\n"
        "🟢 *Добавить рецепт:* три способа\n"
        "  • «Рецепт по ссылке» — вставь URL\n"
        "  • «Рецепт текстом» — вставь текст в любом формате\n"
        "  • Просто *пришли фото* рецепта (страница книги, скрин Pinterest и т.п.)\n\n"
        "🟢 *Закупка и таймлайн:* открой Mini App, выбери событие — там список ингредиентов и план готовки\n\n"
        "🟢 *Календарь:* в Mini App у каждого события есть кнопка «Добавить в календарь» — скачает .ics, добавится в любой календарь (Google, Apple, Outlook)\n\n"
        "🟢 *Напоминания:* за сутки до события я пришлю тебе сообщение",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )


# --- New event FSM ---

async def start_new_event(message: Message, state: FSMContext):
    await state.set_state(NewEvent.title)
    await message.answer("📅 Как назовём мероприятие?")


async def new_event_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(NewEvent.date)
    await message.answer(
        "📆 Укажи дату и время (например: 25.12.2025 19:00)\n"
        "Или отправь /skip чтобы пропустить."
    )


async def new_event_skip_date(message: Message, state: FSMContext):
    await state.update_data(date=None)
    await state.set_state(NewEvent.guests)
    await message.answer("👥 Сколько гостей ожидается? (число)")


async def new_event_date(message: Message, state: FSMContext):
    text = message.text.strip()
    date_iso: str | None = None
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt)
            date_iso = dt.isoformat()
            break
        except ValueError:
            continue
    if not date_iso:
        await message.answer("⚠️ Не понял дату. Попробуй формат: 25.12.2025 19:00")
        return
    await state.update_data(date=date_iso)
    await state.set_state(NewEvent.guests)
    await message.answer("👥 Сколько гостей ожидается? (число)")


async def new_event_guests(message: Message, state: FSMContext):
    try:
        guests = int(message.text.strip())
        if guests < 1:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("⚠️ Введи целое число больше 0.")
        return

    data = await state.get_data()
    await state.clear()

    payload = {
        "title": data["title"],
        "guests_count": guests,
        "date": data.get("date"),
        "telegram_user_id": message.from_user.id if message.from_user else None,
    }
    result = await api_post("/events/", payload)

    if result:
        date_str = f"\n📆 {data['date'][:16].replace('T', ' ')}" if data.get("date") else ""
        reminder_note = "\n\n⏰ За сутки до события я тебе напомню." if data.get("date") else ""
        await message.answer(
            f"✅ Мероприятие создано!\n\n"
            f"*{result['title']}*{date_str}\n"
            f"👥 Гостей: {guests}{reminder_note}\n\n"
            f"Добавь рецепты — нажми кнопку ниже или открой Mini App.",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )
    else:
        await message.answer("❌ Не удалось создать мероприятие.", reply_markup=main_kb())


# --- Import URL ---

async def start_import_url(message: Message, state: FSMContext):
    await state.set_state(ImportUrl.waiting_for_url)
    await message.answer(
        "🔗 Пришли мне ссылку на рецепт.\n"
        "Лучше всего работает с povarenok.ru, 1000.menu, gastronom.ru.\n\n"
        "Для отмены: /cancel"
    )


async def import_url_receive(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_kb())
        return

    url = (message.text or "").strip()
    if not url.startswith("http"):
        await message.answer("Это не похоже на ссылку. Попробуй ещё раз или /cancel")
        return

    await state.clear()
    wait = await message.answer("⏳ Парсю рецепт, подожди 10-20 сек...")
    result = await api_post("/recipes/import", {"url": url})
    await wait.delete()

    if result:
        ing_count = len(result.get("ingredients", []))
        await message.answer(
            f"✅ Рецепт импортирован!\n\n"
            f"*{result['title']}*\n"
            f"🍽 Порций: {result.get('base_servings', '?')}\n"
            f"🥕 Ингредиентов: {ing_count}",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )
    else:
        await message.answer(
            "❌ Не удалось импортировать. Возможно сайт не поддерживается или ссылка битая.\n\n"
            "Попробуй *📝 Рецепт текстом* или пришли *📷 фото* — это сработает с любого сайта.",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )


# --- Import text ---

async def start_import_text(message: Message, state: FSMContext):
    await state.set_state(ImportText.waiting_for_text)
    await message.answer(
        "📝 Пришли мне текст рецепта одним сообщением.\n\n"
        "Можно вставить список ингредиентов + способ готовки в любом формате — "
        "я распознаю через LLM.\n\n"
        "Для отмены: /cancel"
    )


async def import_text_receive(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_kb())
        return

    await state.clear()
    wait = await message.answer("⏳ Распознаю текст через LLM, подожди 10-15 сек...")
    result = await api_post("/recipes/import-text", {"text": message.text or "", "title": None})
    await wait.delete()

    if result:
        ing_count = len(result.get("ingredients", []))
        await message.answer(
            f"✅ Рецепт сохранён!\n\n"
            f"*{result['title']}*\n"
            f"🍽 Порций: {result.get('base_servings', '?')}\n"
            f"🥕 Ингредиентов: {ing_count}",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )
    else:
        await message.answer("❌ Не получилось распознать. Попробуй ещё раз.", reply_markup=main_kb())


# --- Photo recognition (auto) ---

async def _download_photo_b64(message: Message, bot: Bot) -> str:
    photo: PhotoSize = max(message.photo, key=lambda p: p.width * p.height)
    file = await bot.get_file(photo.file_id)
    buf = BytesIO()
    await bot.download(file, destination=buf)
    return base64.b64encode(buf.getvalue()).decode()


# Buffer for Telegram album messages — same media_group_id arrives as N separate messages
_media_groups: dict[str, dict] = {}


async def _flush_media_group(bot: Bot, gid: str):
    """Wait ~2.5s for the rest of the album to arrive, then send ALL images to LLM as ONE recipe."""
    await asyncio.sleep(2.5)
    entry = _media_groups.pop(gid, None)
    if not entry:
        return
    images = entry["images"]
    caption = entry["caption"]
    message = entry["message"]

    wait = await message.answer(
        f"📷 Распознаю рецепт с {len(images)} фото через LLM, подожди 20-30 сек..."
    )
    result = await api_post(
        "/recipes/import-image",
        {"images_base64": images, "title": caption},
    )
    try:
        await wait.delete()
    except Exception:
        pass

    if result:
        ing_count = len(result.get("ingredients", []))
        await message.answer(
            f"✅ Рецепт распознан с {len(images)} фото!\n\n"
            f"*{result['title']}*\n"
            f"🍽 Порций: {result.get('base_servings', '?')}\n"
            f"🥕 Ингредиентов: {ing_count}\n\n"
            f"Если что-то распозналось неправильно — поправь вручную в Mini App.",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )
    else:
        await message.answer(
            "❌ Не получилось распознать рецепт с этих фото. "
            "Попробуй прислать более чёткие фото.",
            reply_markup=main_kb(),
        )


async def handle_photo(message: Message, bot: Bot):
    """Auto-parse incoming photo(s) as ONE recipe.
    Telegram album → all images combined into a single multi-image LLM call."""
    if not message.photo:
        return

    image_b64 = await _download_photo_b64(message, bot)
    caption = (message.caption or "").strip() or None

    gid = message.media_group_id
    if gid:
        if gid in _media_groups:
            _media_groups[gid]["images"].append(image_b64)
            if caption and not _media_groups[gid]["caption"]:
                _media_groups[gid]["caption"] = caption
        else:
            _media_groups[gid] = {"images": [image_b64], "caption": caption, "message": message}
            asyncio.create_task(_flush_media_group(bot, gid))
        return

    # Single photo path
    wait = await message.answer("📷 Распознаю рецепт с фото через LLM, подожди 15-20 сек...")
    result = await api_post("/recipes/import-image", {"image_base64": image_b64, "title": caption})
    try:
        await wait.delete()
    except Exception:
        pass

    if result:
        ing_count = len(result.get("ingredients", []))
        await message.answer(
            f"✅ Рецепт распознан с фото!\n\n"
            f"*{result['title']}*\n"
            f"🍽 Порций: {result.get('base_servings', '?')}\n"
            f"🥕 Ингредиентов: {ing_count}\n\n"
            f"Если что-то распозналось неправильно — поправь вручную в Mini App.",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )
    else:
        await message.answer(
            "❌ Не получилось распознать рецепт. "
            "Попробуй более чёткое фото или скриншот.",
            reply_markup=main_kb(),
        )


async def photo_hint(message: Message):
    """When user clicks '📷 Рецепт с фото' button — just explain."""
    await message.answer(
        "📷 Просто *пришли мне фото* рецепта одним сообщением — "
        "я сам его распознаю.\n\n"
        "Подойдёт страница книги, скриншот Pinterest/Instagram, рукописный рецепт и т.п.",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Commands
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_start, Command("menu"))

    # Button-text matching (must come BEFORE FSM handlers so buttons always work)
    dp.message.register(start_new_event, F.text == BTN_NEW_EVENT)
    dp.message.register(start_import_url, F.text == BTN_IMPORT_URL)
    dp.message.register(start_import_text, F.text == BTN_IMPORT_TEXT)
    dp.message.register(photo_hint, F.text == BTN_IMPORT_PHOTO_INFO)
    dp.message.register(show_help, F.text == BTN_HELP)

    # FSM: new_event
    dp.message.register(new_event_title, NewEvent.title)
    dp.message.register(new_event_skip_date, NewEvent.date, Command("skip"))
    dp.message.register(new_event_date, NewEvent.date)
    dp.message.register(new_event_guests, NewEvent.guests)

    # FSM: import url / text
    dp.message.register(import_url_receive, ImportUrl.waiting_for_url)
    dp.message.register(import_text_receive, ImportText.waiting_for_text)

    # Photos — auto-parse
    dp.message.register(handle_photo, F.photo)

    log.info("Bot started (polling)...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
