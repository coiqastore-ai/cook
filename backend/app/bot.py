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
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonWebApp,
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

BTN_OPEN_APP = "📲 Открыть Поляну"
BTN_NEW_EVENT = "➕ Новое событие"
BTN_IMPORT_RECIPE = "🍳 Добавить рецепт"
BTN_HELP = "❓ Помощь"

# Inline-submenu callback prefixes
CB_IMPORT_URL = "import_url"
CB_IMPORT_TEXT = "import_text"
CB_IMPORT_VOICE = "import_voice"
CB_IMPORT_PHOTO = "import_photo"


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_OPEN_APP, web_app=WebAppInfo(url=settings.miniapp_url))],
            [KeyboardButton(text=BTN_NEW_EVENT), KeyboardButton(text=BTN_IMPORT_RECIPE)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def import_inline_kb() -> InlineKeyboardMarkup:
    """Submenu shown after user taps 'Добавить рецепт'."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 По ссылке", callback_data=CB_IMPORT_URL)],
        [InlineKeyboardButton(text="📝 Текстом", callback_data=CB_IMPORT_TEXT)],
        [InlineKeyboardButton(text="🎤 Голосом", callback_data=CB_IMPORT_VOICE)],
        [InlineKeyboardButton(text="📷 Фото / скриншот", callback_data=CB_IMPORT_PHOTO)],
    ])


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

    # Force per-chat menu button to override any cached old value (e.g. coiqa.ru → cook.coiqa.ru)
    try:
        await message.bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=MenuButtonWebApp(
                text="Открыть Поляну",
                web_app=WebAppInfo(url=settings.miniapp_url),
            ),
        )
    except Exception as e:
        log.warning("Failed to set per-chat menu button: %s", e)

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
        "🌳 *Поляна* — помогаю планировать застолья.\n\n"
        "Что я умею:\n"
        "• Создавать события для застолий с друзьями\n"
        "• Импортировать рецепты — по ссылке, тексту, голосом или с фото\n"
        "• Собирать единый список закупок по событию\n"
        "• Напоминать о событии за сутки\n"
        "• Совместная редактура меню с друзьями\n"
        "• Красивое меню для гостей в PDF\n\n"
        "Выбери действие на клавиатуре снизу 👇",
        parse_mode="Markdown",
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


# --- Import recipe (menu hub) ---

async def show_import_menu(message: Message):
    """Show the inline submenu with 4 import options + reliability hint."""
    await message.answer(
        "🍳 *Как добавить рецепт?*\n\n"
        "Я понимаю 4 способа — выбери удобный:\n"
        "🔗 *По ссылке* — лучше всего работает с povarenok.ru, 1000.menu, gastronom.ru. "
        "Сложные сайты (Pinterest, Instagram, рекламные блоги) могут не распознаваться — тогда используй фото или текст.\n"
        "📝 *Текстом* — вставь рецепт в любом формате одним сообщением\n"
        "🎤 *Голосом* — надиктуй рецепт голосовым сообщением\n"
        "📷 *Фото* — пришли скриншот или фото страницы (можно несколько фото альбомом)\n\n"
        "_⚠ Если что-то распозналось неправильно — поправь руками в Mini App. Каждый ингредиент можно добавить, изменить или удалить._",
        parse_mode="Markdown",
        reply_markup=import_inline_kb(),
    )


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
    result = await api_post("/recipes/import", {
        "url": url,
        "telegram_user_id": message.from_user.id if message.from_user else None,
    })
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
    result = await api_post("/recipes/import-text", {
        "text": message.text or "",
        "title": None,
        "telegram_user_id": message.from_user.id if message.from_user else None,
    })
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
        {
            "images_base64": images,
            "title": caption,
            "telegram_user_id": message.from_user.id if message.from_user else None,
        },
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
    result = await api_post("/recipes/import-image", {
        "image_base64": image_b64,
        "title": caption,
        "telegram_user_id": message.from_user.id if message.from_user else None,
    })
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


# --- Callback handlers for inline import submenu ---

async def cb_import_url(query: CallbackQuery, state: FSMContext):
    await query.answer()
    if query.message:
        await query.message.answer(
            "🔗 Пришли мне ссылку на рецепт.\n"
            "Лучше всего работает с povarenok.ru, 1000.menu, gastronom.ru.\n\n"
            "Для отмены: /cancel"
        )
    await state.set_state(ImportUrl.waiting_for_url)


async def cb_import_text(query: CallbackQuery, state: FSMContext):
    await query.answer()
    if query.message:
        await query.message.answer(
            "📝 Пришли мне текст рецепта одним сообщением.\n\n"
            "Можно вставить список ингредиентов + способ готовки в любом формате — "
            "я распознаю через LLM.\n\n"
            "_Если получилось криво — поправь руками в Mini App._\n\n"
            "Для отмены: /cancel",
            parse_mode="Markdown",
        )
    await state.set_state(ImportText.waiting_for_text)


async def cb_import_voice(query: CallbackQuery):
    await query.answer()
    if query.message:
        await query.message.answer(
            "🎤 Просто *запиши голосовое сообщение* с рецептом — "
            "я расшифрую через Whisper и распознаю.\n\n"
            "Совет: говори чётко, перечисляй ингредиенты и количество "
            "(например: «двести грамм муки, три яйца, столовая ложка сахара…»).",
            parse_mode="Markdown",
        )


async def cb_import_photo(query: CallbackQuery):
    await query.answer()
    if query.message:
        await query.message.answer(
            "📷 Просто *пришли мне фото* рецепта одним сообщением (или альбомом).\n\n"
            "Подойдёт страница книги, скриншот Pinterest/Instagram, рукописный рецепт и т.п.",
            parse_mode="Markdown",
        )


# --- Voice recognition handler (Whisper) ---

async def handle_voice(message: Message, bot: Bot):
    """Auto-transcribe voice/audio via Whisper, then parse the transcript as recipe."""
    file_obj = message.voice or message.audio
    if not file_obj:
        return

    wait = await message.answer("🎤 Слушаю и расшифровываю через Whisper, подожди 10-20 сек...")

    file = await bot.get_file(file_obj.file_id)
    buf = BytesIO()
    await bot.download(file, destination=buf)

    # Transcribe
    try:
        from app.services.llm import transcribe_audio
        transcript = await transcribe_audio(buf.getvalue(), filename="voice.ogg")
    except RuntimeError as e:
        try: await wait.delete()
        except Exception: pass
        await message.answer(
            "❌ Голосовой ввод не настроен (нет `OPENAI_API_KEY`). Попроси администратора.",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )
        log.warning("transcribe failed: %s", e)
        return
    except Exception as e:
        try: await wait.delete()
        except Exception: pass
        await message.answer(f"❌ Не получилось расшифровать: {e}", reply_markup=main_kb())
        return

    if not transcript:
        try: await wait.delete()
        except Exception: pass
        await message.answer("❌ Не удалось распознать речь. Попробуй ещё раз.", reply_markup=main_kb())
        return

    # Parse transcript as recipe text
    result = await api_post("/recipes/import-text", {
        "text": transcript,
        "title": None,
        "telegram_user_id": message.from_user.id if message.from_user else None,
    })
    try: await wait.delete()
    except Exception: pass

    if result:
        ing_count = len(result.get("ingredients", []))
        await message.answer(
            f"✅ Рецепт распознан с голоса!\n\n"
            f"*{result['title']}*\n"
            f"🍽 Порций: {result.get('base_servings', '?')}\n"
            f"🥕 Ингредиентов: {ing_count}\n\n"
            f"_Если что-то криво — поправь в Mini App._",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )
    else:
        await message.answer(
            f"⚠️ Расшифровал голос: «{transcript[:200]}»\n\n"
            f"Но не смог распознать как рецепт. Попробуй надиктовать чётче с ингредиентами и количеством.",
            reply_markup=main_kb(),
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _configure_bot_menu(bot: Bot):
    """Force-set the bot's Menu Button to our Mini App URL.
    Overrides whatever was set via BotFather — guarantees correctness."""
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text="Открыть Поляну",
            web_app=WebAppInfo(url=settings.miniapp_url),
        ))
        log.info("Menu button set to WebApp URL: %s", settings.miniapp_url)
    except Exception as e:
        log.warning("Failed to set menu button: %s", e)


async def main():
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    await _configure_bot_menu(bot)

    # Commands
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_start, Command("menu"))

    # Button-text matching (must come BEFORE FSM handlers so buttons always work)
    dp.message.register(start_new_event, F.text == BTN_NEW_EVENT)
    dp.message.register(show_import_menu, F.text == BTN_IMPORT_RECIPE)
    dp.message.register(show_help, F.text == BTN_HELP)

    # Inline callback handlers (submenu of "Добавить рецепт")
    dp.callback_query.register(cb_import_url, F.data == CB_IMPORT_URL)
    dp.callback_query.register(cb_import_text, F.data == CB_IMPORT_TEXT)
    dp.callback_query.register(cb_import_voice, F.data == CB_IMPORT_VOICE)
    dp.callback_query.register(cb_import_photo, F.data == CB_IMPORT_PHOTO)

    # FSM: new_event
    dp.message.register(new_event_title, NewEvent.title)
    dp.message.register(new_event_skip_date, NewEvent.date, Command("skip"))
    dp.message.register(new_event_date, NewEvent.date)
    dp.message.register(new_event_guests, NewEvent.guests)

    # FSM: import url / text
    dp.message.register(import_url_receive, ImportUrl.waiting_for_url)
    dp.message.register(import_text_receive, ImportText.waiting_for_text)

    # Photos & voice — auto-parse (no command needed)
    dp.message.register(handle_photo, F.photo)
    dp.message.register(handle_voice, F.voice | F.audio)

    log.info("Bot started (polling)...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
