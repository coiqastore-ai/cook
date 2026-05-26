"""Telegram WebApp initData validation (HMAC-SHA256 per Telegram docs).

Two ways to authenticate API calls:
  1. Mini App → sends header `X-Telegram-Init-Data` with raw initData string;
     we verify HMAC against BOT_TOKEN.
  2. Bot process → sends header `X-Internal-API-Key` matching INTERNAL_API_KEY env;
     trusted as bot is internal Docker service. user_id is passed in request body/query.
"""
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, Query

from app.config import settings

# Max age of initData before we consider it stale (anti-replay)
_INIT_DATA_MAX_AGE_SEC = 24 * 3600


def validate_init_data(init_data: str, bot_token: str, max_age_sec: int = _INIT_DATA_MAX_AGE_SEC) -> dict[str, Any] | None:
    """Verify Telegram WebApp initData signature. Return parsed user dict or None on failure."""
    if not init_data or not bot_token:
        return None

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    # Anti-replay: reject old initData
    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError:
        return None
    if auth_date <= 0 or (time.time() - auth_date) > max_age_sec:
        return None

    # Build data_check_string per Telegram spec: sorted key=value joined by \n
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    # Secret key derivation per Telegram WebApp docs
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(received_hash, expected):
        return None

    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        user = json.loads(user_raw)
    except Exception:
        return None
    if not isinstance(user, dict) or "id" not in user:
        return None
    return user


async def get_current_user_id(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-API-Key"),
    auth_uid: int | None = Query(default=None),
) -> int:
    """FastAPI dependency. Returns authenticated Telegram user_id.

    - Mini App: must send X-Telegram-Init-Data header (verified via HMAC).
    - Internal bot calls: must send X-Internal-API-Key header + provide user_id via ?auth_uid=.

    Note: query param is named `auth_uid` (not `telegram_user_id`) to avoid colliding
    with `{telegram_user_id}` path params used in some routes.
    """
    if settings.internal_api_key and x_internal_api_key:
        if hmac.compare_digest(x_internal_api_key, settings.internal_api_key):
            if auth_uid is None:
                raise HTTPException(400, "auth_uid query param required for internal calls")
            return auth_uid

    if x_telegram_init_data:
        user = validate_init_data(x_telegram_init_data, settings.bot_token)
        if user:
            return int(user["id"])
        raise HTTPException(401, "Invalid Telegram initData (bad signature or expired)")

    raise HTTPException(401, "Authentication required (missing initData)")


async def get_current_user_id_optional(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-API-Key"),
    auth_uid: int | None = Query(default=None),
) -> int | None:
    try:
        return await get_current_user_id(x_telegram_init_data, x_internal_api_key, auth_uid)
    except HTTPException:
        return None
