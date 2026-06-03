import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analytics, calendar, events, recipes, shopping, timeline
from app.config import settings
from app.services.reminders import reminder_loop

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def _ensure_analytics_table() -> None:
    """Idempotently create the analytics_events table (deploy runs no migrations).
    create_all(checkfirst=True) only creates missing tables — existing ones untouched."""
    try:
        from app.db import engine
        from app.models import AnalyticsEvent  # noqa: F401 — register on metadata
        from app.models.base import Base

        async with engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[AnalyticsEvent.__table__],
                checkfirst=True,
            )
        log.info("analytics_events table ready")
    except Exception:
        log.exception("failed to ensure analytics_events table")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _ensure_analytics_table()
    # Start background reminder loop
    task = asyncio.create_task(reminder_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="Поляна API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.miniapp_url,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://cook.coiqa.ru",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router)
app.include_router(recipes.router)
app.include_router(shopping.router)
app.include_router(timeline.router)
app.include_router(calendar.router)
app.include_router(analytics.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
