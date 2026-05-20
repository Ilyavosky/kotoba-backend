"""
Integration tests: JWT authentication

Covers:
  - No Authorization header → 401
  - Invalid token signature → 401
  - Expired token → 401
  - Valid token → 200 + correct user payload
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.main import app

#Test constants
TEST_SECRET = "test-secret-only-for-pytest-never-use-in-prod!"
TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_EMAIL = "ilya@kotoba.test"


def _make_token(
    *,
    secret: str = TEST_SECRET,
    user_id: str = TEST_USER_ID,
    email: str = TEST_EMAIL,
    audience: str = "authenticated",
    exp_offset: int = 3600,
) -> str:
    """Builds a signed JWT with the given parameters."""
    now = int(datetime.now(timezone.utc).timestamp())
    return jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "role": "authenticated",
            "aud": audience,
            "iat": now,
            "exp": now + exp_offset,
        },
        secret,
        algorithm="HS256",
    )


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.core.config as config_module
    monkeypatch.setattr(config_module.settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    return TestClient(app, raise_server_exceptions=False)


# /health is always public

def test_health_is_public(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


# Protected route: GET /v1/me

def test_no_token_returns_401(client: TestClient) -> None:
    assert client.get("/v1/me").status_code == 401


def test_invalid_signature_returns_401(client: TestClient) -> None:
    token = _make_token(secret="wrong-secret-completely-different!")
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_expired_token_returns_401(client: TestClient) -> None:
    token = _make_token(exp_offset=-1)
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_malformed_token_returns_401(client: TestClient) -> None:
    assert client.get("/v1/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_valid_token_returns_200(client: TestClient) -> None:
    token = _make_token()
    response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200