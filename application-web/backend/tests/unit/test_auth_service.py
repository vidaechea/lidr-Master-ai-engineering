from __future__ import annotations

import pytest

from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)


class TestHashPassword:
    def test_hash_differs_from_plain(self):
        hashed = hash_password("mysecret")
        assert hashed != "mysecret"

    def test_different_calls_produce_different_hashes(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2  # bcrypt salts are random per call


class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        hashed = hash_password("correct")
        assert verify_password("correct", hashed) is True

    def test_wrong_password_returns_false(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_empty_string_does_not_match_non_empty_hash(self):
        hashed = hash_password("nonempty")
        assert verify_password("", hashed) is False


class TestCreateAccessToken:
    def test_token_is_a_string(self):
        token = create_access_token("user-123")
        assert isinstance(token, str)

    def test_token_has_three_dot_separated_parts(self):
        token = create_access_token("user-123")
        assert len(token.split(".")) == 3

    def test_token_encodes_user_id_and_type(self):
        from jose import jwt
        from app.config import settings

        token = create_access_token("user-abc")
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert payload["sub"] == "user-abc"
        assert payload["type"] == "access"

    def test_token_has_exp_claim(self):
        from jose import jwt
        from app.config import settings

        token = create_access_token("user-abc")
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert "exp" in payload


class TestCreateRefreshToken:
    def test_token_has_refresh_type(self):
        from jose import jwt
        from app.config import settings

        token = create_refresh_token("user-456")
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert payload["type"] == "refresh"
        assert payload["sub"] == "user-456"

    def test_access_and_refresh_tokens_differ(self):
        user_id = "user-999"
        assert create_access_token(user_id) != create_refresh_token(user_id)


class TestDecodeRefreshToken:
    def test_returns_user_id_for_valid_token(self):
        token = create_refresh_token("user-789")
        assert decode_refresh_token(token) == "user-789"

    def test_raises_value_error_for_access_token(self):
        token = create_access_token("user-789")
        with pytest.raises(ValueError, match="Not a refresh token"):
            decode_refresh_token(token)

    def test_raises_value_error_for_garbage_token(self):
        with pytest.raises(ValueError, match="Invalid or expired refresh token"):
            decode_refresh_token("not.a.valid.jwt")

    def test_raises_value_error_for_empty_string(self):
        with pytest.raises(ValueError):
            decode_refresh_token("")
