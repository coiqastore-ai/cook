"""Telegram bot — запускается отдельно: uv run python -m app.bot_runner"""
import asyncio
import base64
import logging
import os
import re
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
    Message,
    PhotoSize,
    WebAppInfo,
)

from app.config import settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# В docker-compose API_BASE=http://backend:8000, локально — fallback на localhost
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")


# ---------------------------------------------------------------------------
# FSM states
# ---------------------------------------------------------------------------

class NewEvent(StatesGroup):
    title = State()
    date = State()
    guests = State()


class ImportText(StatesGroup):
    waiting_for_text = State()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def api_post(path: str, data: dict) -> dict | None:
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(f"{API_BASE}{path}", json=data)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.error("API POST %s failed: %s", path, e)
            return None


async def api_get(path: str) -> dict | list | None:
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.get(f"{API_BASE}{path}")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.error("API GET %s failed: %s", path, e)
            return None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def open_app_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📱 Открыть приложение", web_app=WebAppInfo(url=settings.miniapp_url))
    ]])


async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я Mealie Bot — помогаю планировать застолья.\n\n"
        "Что умею:\n"
        "• /new_event — создать мероприятие\n"
        "• /import_recipe <url> — импортировать рецепт по ссылке\n"
        "• /import_text — импортировать рецепт текстом\n"
        "• 📷 Просто пришли фото рецепта (страница книги, скрин Pinterest и т.п.)\n"
        "• /sync_calendar — синхронизировать с Google Calendar\n\n"
        "Или открой Mini App для полного интерфейса 👇",
        reply_markup=open_app_kb(),
    )


# --- /new_event FSM ---

async def cmd_new_event(message: Message, state: FSMContext):
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
    text = message.text.strip()
    try:
        guests = int(text)
        if guests < 1:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введи целое число больше 0.")
        return

    data = await state.get_data()
    await state.clear()

    payload = {"title": data["title"], "guests_count": guests, "date": data.get("date")}
    result = await api_post("/events/", payload)

    if result:
        date_str = f"\n📆 {data['date'][:10]}" if data.get("date") else ""
        await message.answer(
            f"✅ Мероприятие создано!\n\n"
            f"*{result['title']}*{date_str}\n"
            f"👥 Гостей: {guests}\n\n"
            f"Добавь рецепты через Mini App 👇",
            parse_mode="Markdown",
            reply_markup=open_app_kb(),
        )
    else:
        await message.answer("❌ Не удалось создать мероприятие. Убедись, что бэкенд запущен.")


# --- /import_recipe ---

async def cmd_import_recipe(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].startswith("http"):
        await message.answer("Использование: /import_recipe <url>\nПример: /import_recipe https://eda.ru/...")
        return

    url = args[1].strip()
    wait_msg = await message.answer("⏳ Парсю рецепт, подожди...")

    result = await api_post("/recipes/import", {"url": url})
    await wait_msg.delete()

    if result:
        ing_count = len(result.get("ingredients", []))
        await message.answer(
            f"✅ Рецепт импортирован!\n\n"
            f"*{result['title']}*\n"
            f"🍽 Порций: {result.get('base_servings', '?')}\n"
            f"🥕 Ингредиентов: {ing_count}\n"
            f"⏱ Готовка: {result.get('cook_time_min') or '?'} мин\n\n"
            f"Добавь к мероприятию в Mini App 👇",
            parse_mode="Markdown",
            reply_markup=open_app_kb(),
        )
    else:
        await message.answer("❌ Не удалось импортировать рецепт. Проверь ссылку или попробуй другой сайт.")


# --- /import_text ---

async def cmd_import_text(message: Message, state: FSMContext):
    await state.set_state(ImportText.waiting_for_text)
    await message.answer(
        "📝 Пришли мне текст рецепта одним сообщением.\n\n"
        "Можно вставить список ингредиентов + способ готовки в любом формате — "
        "я попробую разобрать через LLM.\n\n"
        "Для отмены: /cancel"
    )


async def import_text_receive(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("Отменено.")
        return

    await state.clear()
    wait_msg = await message.answer("⏳ Парсю текст рецепта через LLM, подожди 10-15 сек...")

    result = await api_post("/recipes/import-text", {"text": message.text or "", "title": None})
    await wait_msg.delete()

    if result:
        ing_count = len(result.get("ingredients", []))
        await message.answer(
            f"✅ Рецепт сохранён!\n\n"
            f"*{result['title']}*\n"
            f"🍽 Порций: {result.get('base_servings', '?')}\n"
            f"🥕 Ингредиентов: {ing_count}\n\n"
            f"Добавь к мероприятию в Mini App 👇",
            parse_mode="Markdown",
            reply_markup=open_app_kb(),
        )
    else:
        await message.answer("❌ Не получилось распознать рецепт. Попробуй ещё раз.")


# --- /sync_calendar ---

async def handle_photo(message: Message, bot: Bot):
    """Auto-parse any incoming photo as a recipe via Qwen Vision."""
    if not message.photo:
        return
    wait = await message.answer("📷 Распознаю рецепт с фото через LLM, подожди 15-20 сек...")

    # Take the largest photo size
    photo: PhotoSize = max(message.photo, key=lambda p: p.width * p.height)
    file = await bot.get_file(photo.file_id)
    buf = BytesIO()
    await bot.download(file, destination=buf)
    image_b64 = base64.b64encode(buf.getvalue()).decode()

    caption = (message.caption or "").strip() or None
    result = await api_post("/recipes/import-image", {"image_base64": image_b64, "title": caption})
    await wait.delete()

    if result:
        ing_count = len(result.get("ingredients", []))
        await message.answer(
            f"✅ Рецепт распознан с фото!\n\n"
            f"*{result['title']}*\n"
            f"🍽 Порций: {result.get('base_servings', '?')}\n"
            f"🥕 Ингредиентов: {ing_count}\n\n"
            f"Если что-то распозналось неправильно — поправь вручную в Mini App 👇",
            parse_mode="Markdown",
            reply_markup=open_app_kb(),
        )
    else:
        await message.answer(
            "❌ Не получилось распознать рецепт с фото. "
            "Попробуй чёткое фото или скриншот с хорошо видимым текстом."
        )


async def cmd_sync_calendar(message: Message):
    # Check if Google Calendar is connected
    status = await api_get("/calendar/status")
    if not status or not status.get("connected"):
        auth = await api_get("/calendar/oauth/start")
        url = auth.get("url") if isinstance(auth, dict) else None
        if url:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔗 Подключить Google Calendar", url=url)
            ]])
            await message.answer(
                "Google Calendar не подключён.\nНажми кнопку для авторизации:",
                reply_markup=kb,
            )
        else:
            await message.answer("❌ Не удалось получить ссылку для авторизации. Убедись, что GOOGLE_CLIENT_ID настроен.")
        return

    wait_msg = await message.answer("🔄 Синхронизирую события...")
    result = await api_post("/calendar/sync", {})
    await wait_msg.delete()

    if result is None:
        await message.answer("❌ Ошибка синхронизации.")
        return

    created = result.get("created", 0)
    updated = result.get("updated", 0)
    await message.answer(
        f"✅ Синхронизация завершена!\n\n"
        f"➕ Создано мероприятий: {created}\n"
        f"🔄 Обновлено: {updated}\n\n"
        f"Посмотри список событий в Mini App 👇",
        reply_markup=open_app_kb(),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_new_event, Command("new_event"))
    dp.message.register(cmd_import_recipe, Command("import_recipe"))
    dp.message.register(cmd_import_text, Command("import_text"))
    dp.message.register(cmd_sync_calendar, Command("sync_calendar"))

    # FSM: new_event flow
    dp.message.register(new_event_title, NewEvent.title)
    dp.message.register(new_event_skip_date, NewEvent.date, Command("skip"))
    dp.message.register(new_event_date, NewEvent.date)
    dp.message.register(new_event_guests, NewEvent.guests)

    # FSM: import_text
    dp.message.register(import_text_receive, ImportText.waiting_for_text)

    # Auto-handle any photo sent to the bot
    dp.message.register(handle_photo, F.photo)

    log.info("Bot started (polling)...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
