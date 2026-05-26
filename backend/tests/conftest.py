"""Shared pytest fixtures."""
import os

import pytest

# Make sure test runs don't accidentally hit production
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://mealie:mealie@localhost:5432/mealie_test")
os.environ.setdefault("BOT_TOKEN", "0000000000:TEST-TOKEN-MUST-BE-LONG-ENOUGH-XXXXXXXXX")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key-32-chars-min-xxxx")


@pytest.fixture
def bot_token() -> str:
    """Stable bot token used to compute test HMAC signatures."""
    return os.environ["BOT_TOKEN"]


@pytest.fixture
def internal_api_key() -> str:
    return os.environ["INTERNAL_API_KEY"]


@pytest.fixture
def fake_user() -> dict:
    """Sample Telegram user payload used in initData strings."""
    return {"id": 100500, "first_name": "Test", "username": "test_user", "language_code": "ru"}


def _make_valid_init_data(user: dict, bot_token: str, auth_date: int | None = None) -> str:
    """Build a valid signed initData string the same way Telegram does."""
    import hashlib
    import hmac
    import json
    import time
    from urllib.parse import urlencode

    auth_date = auth_date or int(time.time())
    fields = {
        "user": json.dumps(user, separators=(",", ":")),
        "auth_date": str(auth_date),
        "query_id": "AAH_test",
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    fields["hash"] = h
    return urlencode(fields)


@pytest.fixture
def valid_init_data(fake_user, bot_token) -> str:
    return _make_valid_init_data(fake_user, bot_token)
