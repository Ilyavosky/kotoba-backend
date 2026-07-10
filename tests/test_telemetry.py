from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.core.deps import get_telemetry_repository
from app.main import app

# Constants

TEST_SECRET = "test-secret-only-for-pytest-never-use-in-prod!"
TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"

# Helpers


def _make_token() -> str:
    now = int(datetime.now(UTC).timestamp())
    return str(jwt.encode(
        {
            "sub": TEST_USER_ID,
            "email": "ilya@kotoba.test",
            "role": "authenticated",
            "aud": "authenticated",
            "iat": now,
            "exp": now + 3600,
        },
        TEST_SECRET,
        algorithm="HS256",
    ))


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_make_token()}"}


def _event(event_type: str = "lesson_started") -> dict:
    return {
        "event_type": event_type,
        "occurred_at": "2026-07-06T12:00:00Z",
        "payload": {"lesson_id": "lesson-001"},
        "app_version": "0.3.1",
        "platform": "android",
    }


# Fixtures


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    return TestClient(app, raise_server_exceptions=False)


@contextmanager
def _override_repo(
    insert_side_effect: Exception | None = None,
) -> Generator[MagicMock, None, None]:
    repo = MagicMock()
    if insert_side_effect:
        repo.insert_events = AsyncMock(side_effect=insert_side_effect)
    else:
        repo.insert_events = AsyncMock(return_value=None)
    app.dependency_overrides[get_telemetry_repository] = lambda: repo
    try:
        yield repo
    finally:
        app.dependency_overrides.clear()


# Tests


def test_ingest_batch_returns_202(client: TestClient) -> None:
    """Happy path: batch accepted, user_id taken from the JWT."""
    with _override_repo() as repo:
        response = client.post(
            "/v1/telemetry/events",
            headers=_auth_headers(),
            json={"events": [_event(), _event("turn_completed")]},
        )

    assert response.status_code == 202
    assert response.json() == {"accepted": 2}
    repo.insert_events.assert_called_once()
    user_id, events = repo.insert_events.call_args.args
    assert user_id == TEST_USER_ID
    assert len(events) == 2
    assert events[0].event_type == "lesson_started"


def test_ingest_requires_auth(client: TestClient) -> None:
    """No JWT -> 401."""
    response = client.post(
        "/v1/telemetry/events", json={"events": [_event()]}
    )
    assert response.status_code == 401


def test_empty_batch_returns_422(client: TestClient) -> None:
    """events must have at least 1 item (pydantic min_length)."""
    with _override_repo():
        response = client.post(
            "/v1/telemetry/events",
            headers=_auth_headers(),
            json={"events": []},
        )
    assert response.status_code == 422


def test_invalid_event_returns_422(client: TestClient) -> None:
    """Empty event_type and bad platform are rejected by validation."""
    bad = _event()
    bad["event_type"] = ""
    with _override_repo():
        response = client.post(
            "/v1/telemetry/events",
            headers=_auth_headers(),
            json={"events": [bad]},
        )
    assert response.status_code == 422


def test_batch_above_limit_returns_413(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "TELEMETRY_MAX_BATCH", 3)
    with _override_repo() as repo:
        response = client.post(
            "/v1/telemetry/events",
            headers=_auth_headers(),
            json={"events": [_event() for _ in range(4)]},
        )

    assert response.status_code == 413
    repo.insert_events.assert_not_called()


def test_storage_failure_returns_502(client: TestClient) -> None:
    """Supabase down -> 502 so the client can retry the same batch."""
    with _override_repo(insert_side_effect=ConnectionError("Supabase down")):
        response = client.post(
            "/v1/telemetry/events",
            headers=_auth_headers(),
            json={"events": [_event()]},
        )
    assert response.status_code == 502
