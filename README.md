# Mealie Bot

Telegram-бот + Vue 3 Mini App + FastAPI backend для планирования застолий.

**Сценарий:** Создаёшь событие → импортируешь рецепты по ссылкам → получаешь агрегированный список закупки и таймлайн готовки. Плюс синхронизация событий из Google Calendar (дни рождения, корпоративы и т.п.).

---

## Технологии

- **Backend:** Python 3.11+, FastAPI, aiogram 3, SQLAlchemy 2 (async), Alembic, PostgreSQL 16
- **Frontend:** Vue 3 + Vite + TailwindCSS
- **LLM:** OpenRouter — Gemini 2.5 Flash (парсинг рецептов, таймлайн) + DeepSeek Chat (нормализация ингредиентов)
- **Менеджеры пакетов:** `uv` (Python), `pnpm` (Node)

## Что нужно установить заранее

| Инструмент | Зачем | Как поставить |
|---|---|---|
| Docker Desktop | PostgreSQL | docker.com |
| uv | Python deps + venv | `pip install uv` |
| Node.js 18+ | Mini App | nodejs.org |
| pnpm | Mini App deps | `npm install -g pnpm` |

---

## Быстрый старт

```bash
git clone <repo>
cd mealie

# 1. Поднять PostgreSQL
docker compose up -d

# 2. Создать .env (см. ниже секцию «Переменные окружения»)
cp .env.example .env
# отредактировать .env, заполнить токены

# 3. Backend
cd backend
uv sync                           # установит зависимости в .venv
cp ../.env .                      # бэкенду нужен .env в backend/
uv run alembic upgrade head       # создать таблицы
uv run uvicorn app.main:app --reload   # API на :8000

# 4. Telegram-бот (в отдельном терминале)
cd backend
uv run python -m app.bot_runner

# 5. Mini App (в третьем терминале)
cd miniapp
pnpm install
pnpm dev                          # http://localhost:5173
```

Открой Swagger: **http://localhost:8000/docs**

---

## Переменные окружения (`.env`)

Файл нужен **в двух местах:** в корне `mealie/.env` и в `mealie/backend/.env`. Содержание одинаковое.

```env
DATABASE_URL=postgresql+asyncpg://mealie:mealie@localhost:5432/mealie

# Telegram
BOT_TOKEN=получить_у_@BotFather

# Mini App
MINIAPP_URL=http://localhost:5173

# OpenRouter (для LLM)
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL_FAST=deepseek/deepseek-chat
OPENROUTER_MODEL_SMART=google/gemini-2.5-flash

# Google Calendar (опционально, для /sync_calendar)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/calendar/oauth/callback
```

### Где взять токены

- **`BOT_TOKEN`** — напиши боту [@BotFather](https://t.me/BotFather) → `/newbot`
- **`OPENROUTER_API_KEY`** — зарегистрируйся на [openrouter.ai](https://openrouter.ai/), пополни баланс, в Settings → Keys создай ключ

---

## Подключение Google Calendar (опционально)

1. Зайди на **console.cloud.google.com**
2. **APIs & Services → Library** → найди **Google Calendar API** → **Enable**
3. **APIs & Services → Credentials** → **+ Create credentials → OAuth client ID**
4. Если попросит — настрой **OAuth consent screen** (User Type: External, добавь свой email в Test users)
5. **Application type: Web application**
6. В **Authorized redirect URIs** добавь **точно**: `http://localhost:8000/calendar/oauth/callback`
7. Скопируй `Client ID` и `Client Secret` в оба `.env` файла
8. Перезапусти бэкенд, открой в браузере: **http://localhost:8000/calendar/oauth/start**
9. Войди в Google → вернёт на Mini App с флагом `?calendar=connected`

После этого:
- Команда `/sync_calendar` в боте
- Кнопка «Синхронизировать Google Calendar» в Mini App

Импортирует события из основного календаря на ближайшие 90 дней. Количество гостей парсится из описания события (regex: `«10 гостей»`, `«5 человек»`, `«guests: 12»` и т.п.).

---

## Архитектура

```
mealie/
├── docker-compose.yml         # postgres:16 + adminer:8080
├── .env / .env.example
│
├── backend/
│   ├── pyproject.toml         # uv project
│   ├── alembic.ini
│   ├── migrations/            # SQL миграции
│   ├── token.json             # OAuth токен Google (создаётся автоматически)
│   └── app/
│       ├── main.py            # FastAPI app + CORS + роутеры
│       ├── bot.py             # aiogram 3 (handlers)
│       ├── bot_runner.py      # entry point: uv run python -m app.bot_runner
│       ├── config.py          # pydantic-settings
│       ├── db.py              # async engine + get_session
│       ├── models/            # 6 SQLAlchemy моделей
│       ├── schemas/           # Pydantic схемы
│       ├── api/               # FastAPI роутеры: events, recipes, shopping, timeline, calendar
│       ├── services/
│       │   ├── llm.py             # OpenRouter клиент, fast()/smart() helpers
│       │   ├── recipe_parser.py   # recipe-scrapers + LLM фолбэк (Gemini)
│       │   ├── normalizer.py      # г/мл/стакан → граммы, densities.json + LLM (DeepSeek)
│       │   ├── aggregator.py      # суммирование, группировка имён (DeepSeek)
│       │   ├── timeline.py        # генерация обратного отсчёта (Gemini)
│       │   └── calendar_sync.py   # Google OAuth (PKCE) + импорт событий
│       └── data/
│           └── densities.json     # ~100 продуктов с плотностями (г/мл)
│
└── miniapp/                   # Vue 3 + Vite + Tailwind
    ├── package.json
    ├── tailwind.config.js
    └── src/
        ├── main.ts
        ├── App.vue            # нижняя навигация
        ├── router.ts          # 5 маршрутов
        ├── api.ts             # типизированный fetch-клиент
        └── views/
            ├── EventsView.vue        # список событий + Google Calendar sync
            ├── EventDetailView.vue   # детали + добавление рецептов
            ├── RecipesView.vue       # библиотека рецептов
            ├── ShoppingView.vue      # чеклист + экспорт
            └── TimelineView.vue      # вертикальный таймлайн
```

---

## Сценарий проверки end-to-end

1. Запусти все 3 части (docker, backend, miniapp)
2. Открой Mini App: `http://localhost:5173`
3. **Создай событие**: «Новый год», 31.12.2026 18:00, 8 гостей
4. Зайди в событие → **+ URL** → вставь ссылку на любой рецепт с eda.ru / 1000.menu / povar.ru
5. Подожди ~10 сек (LLM парсит) → рецепт появится с ингредиентами
6. **+ URL** ещё один рецепт
7. Установи множитель порций (например, ×2)
8. Нажми **🛒 Закупка** — должен сгенерироваться агрегированный список (LLM сгруппирует «мука пшеничная» и «мука в/с» в одну позицию)
9. Поставь галочки, нажми **Экспорт** — скопируется в буфер обмена
10. Назад → **⏱ Таймлайн** → нажми **Обновить** → LLM сгенерирует план готовки с обратным отсчётом

Параллельно проверь бота:
- `/start` — приветствие с кнопкой Mini App
- `/new_event` — диалог создания
- `/import_recipe <url>` — импорт рецепта
- `/sync_calendar` — синхронизация Google Calendar

---

## API эндпоинты

Swagger: **http://localhost:8000/docs**

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/events/` | Список событий |
| `POST` | `/events/` | Создать событие |
| `GET` | `/events/{id}` | Детали события (с рецептами) |
| `PATCH` | `/events/{id}` | Обновить |
| `DELETE` | `/events/{id}` | Удалить |
| `POST` | `/events/{id}/recipes` | Привязать рецепт |
| `PATCH` | `/events/{id}/recipes/{rid}` | Изменить множитель |
| `DELETE` | `/events/{id}/recipes/{rid}` | Отвязать рецепт |
| `GET` | `/recipes/` | Список рецептов |
| `POST` | `/recipes/import` | Импорт по URL |
| `GET` | `/recipes/{id}` | Детали рецепта |
| `GET` | `/shopping/{eid}` | Список закупки (агрегирует) |
| `PATCH` | `/shopping/{eid}/items/{iid}` | Отметить куплено |
| `GET` | `/shopping/{eid}/export` | Текстовый экспорт |
| `GET` | `/timeline/{eid}` | Таймлайн (кеш или генерация) |
| `POST` | `/timeline/{eid}/regenerate` | Перегенерировать |
| `GET` | `/calendar/status` | Подключён ли Google |
| `GET` | `/calendar/oauth/start` | Начать OAuth (302 → Google) |
| `GET` | `/calendar/oauth/callback` | OAuth callback |
| `POST` | `/calendar/sync` | Импортировать события |

---

## Распределение моделей LLM

Чтобы экономить токены — две модели под разные задачи:

| Задача | Модель | Почему |
|---|---|---|
| Парсинг рецептов из HTML (fallback) | Gemini 2.5 Flash | Длинный контекст, нужно понимать страницу |
| Генерация таймлайна готовки | Gemini 2.5 Flash | Нужны общие знания о готовке |
| Нормализация единиц измерения | DeepSeek Chat | Простые конвертации, дешевле |
| Группировка названий ингредиентов | DeepSeek Chat | Короткая семантика, дешевле |

Менять модели — в `.env` через `OPENROUTER_MODEL_FAST` и `OPENROUTER_MODEL_SMART`.

---

## Решение типичных проблем

### `docker: command not found`
Открой Docker Desktop вручную из меню Пуск.

### `cd D:\... ` не меняет диск
В Windows CMD используй `cd /d D:\path` или PowerShell.

### `uv run uvicorn` → `program not found`
Ты не в папке `backend/`. Сначала: `cd /d D:\BOTS\coooookies\mealie\backend`

### `redirect_uri_mismatch` при Google OAuth
В Google Cloud Console → Credentials → твой OAuth client → Authorized redirect URIs добавь **точно**: `http://localhost:8000/calendar/oauth/callback`. Подожди 1-2 минуты после сохранения.

### `Missing code verifier` при Google OAuth
Кеш браузера, открой в инкогнито: `Ctrl+Shift+N` → `http://localhost:8000/calendar/oauth/start`

### `/calendar/sync` возвращает `{"created":0,"updated":0}`
В Google Calendar того аккаунта, под которым ты авторизовался, **нет событий** в ближайшие 90 дней. Добавь тестовое событие или переподключись:
```bash
del backend\token.json
# затем снова /calendar/oauth/start
```

### Mini App не может достучаться до бэкенда
Проверь CORS в `backend/app/main.py` — должен быть разрешён `http://localhost:5173`.

---

## Готовность

- `docker compose up -d` поднимает PostgreSQL ✅
- `uv run alembic upgrade head` применяет миграции (6 таблиц) ✅
- `uv run uvicorn app.main:app --reload` — API на :8000, Swagger на /docs ✅
- `uv run python -m app.bot_runner` — Telegram-бот в polling ✅
- `pnpm dev` в `miniapp/` — Mini App на :5173 ✅
- Сквозной сценарий: событие → 2 рецепта по URL → агрегированный список → таймлайн ✅
- Google Calendar OAuth + импорт событий ✅
