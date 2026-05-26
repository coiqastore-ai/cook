"""Auth — Telegram WebApp initData HMAC validation."""
import time
from urllib.parse import urlencode

import pytest

from app.auth import validate_init_data


class TestValidateInitData:
    def test_valid_init_data_returns_user(self, valid_init_data, bot_token, fake_user):
        """Business rule: a properly signed initData must return the user dict."""
        user = validate_init_data(valid_init_data, bot_token)
        assert user is not None
        assert user["id"] == fake_user["id"]
        assert user["username"] == fake_user["username"]

    def test_tampered_user_field_is_rejected(self, valid_init_data, bot_token):
        """Security: changing any field (e.g. user id) invalidates the signature."""
        # Replace user payload with a different id but keep the original hash
        parts = dict(p.split("=", 1) for p in valid_init_data.split("&"))
        parts["user"] = urlencode({"u": '{"id":999,"username":"attacker"}'})["u=".__len__():]  # ugly but works
        forged = urlencode(parts)
        assert validate_init_data(forged, bot_token) is None

    def test_wrong_hash_is_rejected(self, valid_init_data, bot_token):
        """Security: arbitrary hash value must be rejected."""
        parts = dict(p.split("=", 1) for p in valid_init_data.split("&"))
        parts["hash"] = "0" * 64
        bad = urlencode(parts)
        assert validate_init_data(bad, bot_token) is None

    def test_missing_hash_is_rejected(self, fake_user, bot_token):
        """Security: initData without a hash field must be rejected outright."""
        bad = urlencode({"user": str(fake_user), "auth_date": str(int(time.time()))})
        assert validate_init_data(bad, bot_token) is None

    def test_wrong_bot_token_rejects(self, valid_init_data):
        """Security: signing key derives from the bot token — using another token fails."""
        assert validate_init_data(valid_init_data, "0:WRONG-TOKEN-VALUE") is None

    def test_empty_init_data_returns_none(self, bot_token):
        assert validate_init_data("", bot_token) is None

    def test_empty_bot_token_returns_none(self, valid_init_data):
        assert validate_init_data(valid_init_data, "") is None

    def test_expired_init_data_is_rejected(self, fake_user, bot_token):
        """Anti-replay: initData older than max_age must be rejected."""
        from tests.conftest import _make_valid_init_data
        old_init = _make_valid_init_data(fake_user, bot_token, auth_date=int(time.time()) - 100_000)
        assert validate_init_data(old_init, bot_token, max_age_sec=3600) is None

    def test_malformed_query_string_returns_none(self, bot_token):
        # parse_qsl is forgiving, but missing required fields should fail validation
        for bad in ["not_a_query_string", "=", "&&&", "hash=xxx"]:
            assert validate_init_data(bad, bot_token) is None
