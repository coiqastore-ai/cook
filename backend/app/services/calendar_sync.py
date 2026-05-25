"""Google Calendar → Mealie Events sync (one-way, read-only)."""
import asyncio
import base64
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx

from app.config import settings

_TOKEN_PATH = Path(__file__).parent.parent.parent / "token.json"
_STATE_PATH = Path(__file__).parent.parent.parent / ".oauth_state.json"
_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
_CALENDAR_IDS = [
    "primary",
    "contactsbirthdays@group.v.calendar.google.com",
]


def _credentials_configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge)."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


# ---------------------------------------------------------------------------
# OAuth flow — state persisted to disk so --reload doesn't break it
# ---------------------------------------------------------------------------

def get_auth_url() -> str:
    if not _credentials_configured():
        raise RuntimeError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set")

    verifier, challenge = _pkce_pair()
    nonce = base64.urlsafe_b64encode(os.urandom(8)).rstrip(b"=").decode()
    # Encode verifier into state so it round-trips through Google without needing disk/memory
    state = f"{nonce}.{verifier}"

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(_SCOPES),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return "https://accounts.google.com/o/oauth2/auth?" + urlencode(params)


def exchange_code(code: str, state: str) -> None:
    if "." not in state:
        raise RuntimeError("Invalid OAuth state — must contain code verifier")
    _nonce, verifier = state.split(".", 1)

    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed: {resp.text}")
    token_data = resp.json()

    _TOKEN_PATH.write_text(
        json.dumps({
            "token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "scopes": _SCOPES,
        }),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def _get_credentials():
    if not _TOKEN_PATH.exists():
        return None
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        return creds if creds.valid else None
    except Exception:
        return None


def is_connected() -> bool:
    return _credentials_configured() and _get_credentials() is not None


# ---------------------------------------------------------------------------
# Fetch events from Google Calendar
# ---------------------------------------------------------------------------

def _fetch_events_sync(days_ahead: int) -> list[dict]:
    from googleapiclient.discovery import build

    creds = _get_credentials()
    if not creds:
        raise RuntimeError("Not authenticated with Google Calendar")

    service = build("calendar", "v3", credentials=creds)
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    events: list[dict] = []
    for cal_id in _CALENDAR_IDS:
        try:
            result = (
                service.events()
                .list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=200,
                )
                .execute()
            )
            for item in result.get("items", []):
                start = item.get("start", {})
                dt = start.get("dateTime") or start.get("date")
                if dt:
                    events.append({
                        "summary": item.get("summary", "Без названия"),
                        "start_datetime": dt,
                        "description": item.get("description") or "",
                    })
        except Exception:
            pass

    return events


async def fetch_events(days_ahead: int = 90) -> list[dict]:
    return await asyncio.to_thread(_fetch_events_sync, days_ahead)


# ---------------------------------------------------------------------------
# Sync to Mealie DB
# ---------------------------------------------------------------------------

def _parse_guests(description: str | None) -> int:
    if not description:
        return 1
    for pattern in [
        r"(\d+)\s*(?:гостей|гостя|гость)",
        r"(\d+)\s*(?:человек|чел\.?)",
        r"(\d+)\s*(?:people|guests?|persons?)",
        r"guests?:\s*(\d+)",
    ]:
        m = re.search(pattern, description, re.IGNORECASE)
        if m:
            return max(1, int(m.group(1)))
    return 1


async def sync_to_mealie(session) -> tuple[int, int]:
    from sqlalchemy import and_, select

    from app.models import Event

    raw = await fetch_events()
    created = updated = 0

    for ev in raw:
        title = ev["summary"]
        dt_str = ev["start_datetime"]

        try:
            if "T" in dt_str:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            else:
                dt = datetime.fromisoformat(dt_str).replace(hour=12, tzinfo=timezone.utc)
        except ValueError:
            continue

        guests = _parse_guests(ev.get("description"))
        notes = ev.get("description") or None
        day_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        result = await session.execute(
            select(Event).where(and_(Event.title == title, Event.date >= day_start, Event.date < day_end))
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.guests_count = guests
            if notes:
                existing.notes = notes
            updated += 1
        else:
            session.add(Event(title=title, date=dt, guests_count=guests, notes=notes))
            created += 1

    await session.commit()
    return created, updated
