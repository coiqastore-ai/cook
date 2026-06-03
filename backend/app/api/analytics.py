"""Lightweight analytics ingest endpoint.

Used by the bot to log events that have no other API footprint (e.g. /start).
Mini App can also call it for client-side funnel steps. Auth via the standard
dependency (initData for Mini App, internal key + auth_uid for the bot).
"""
from fastapi import APIRouter, Depends

from app.auth import get_current_user_id
from app.services.analytics import track

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/track", status_code=202)
async def track_event(
    body: dict,
    user_id: int = Depends(get_current_user_id),
):
    event_type = str(body.get("event_type") or "")
    if not event_type:
        return {"ok": False}
    props = body.get("props")
    await track(
        user_id,
        event_type,
        props=props if isinstance(props, dict) else {},
        src_payload=(str(body["src_payload"]) if body.get("src_payload") else None),
    )
    return {"ok": True}
