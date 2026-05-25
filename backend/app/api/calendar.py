from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.services import calendar_sync

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/status")
async def status():
    return {"connected": calendar_sync.is_connected()}


@router.get("/oauth/start")
async def oauth_start():
    try:
        url = calendar_sync.get_auth_url()
        return RedirectResponse(url=url, status_code=302)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.get("/oauth/callback")
async def oauth_callback(code: str, state: str):
    try:
        calendar_sync.exchange_code(code, state)
    except Exception as e:
        raise HTTPException(400, f"OAuth failed: {e}")
    return RedirectResponse(url=settings.miniapp_url + "?calendar=connected")


@router.post("/sync")
async def sync(session: AsyncSession = Depends(get_session)):
    if not calendar_sync.is_connected():
        raise HTTPException(401, "Google Calendar not connected. Visit /calendar/oauth/start first.")
    try:
        created, updated = await calendar_sync.sync_to_mealie(session)
        return {"created": created, "updated": updated}
    except Exception as e:
        raise HTTPException(500, f"Sync failed: {e}")
