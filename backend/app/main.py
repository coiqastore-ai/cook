from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import calendar, events, recipes, shopping, timeline
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # tables are managed by alembic


app = FastAPI(title="Mealie Bot API", version="0.1.0", lifespan=lifespan)

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


@app.get("/health")
async def health():
    return {"status": "ok"}
