"""
K-07.2 — /turn stability under load

Unit + integration tests for the three protections added to /turn:
- 413 when the audio upload exceeds MAX_AUDIO_BYTES
- 429 when a user exceeds RATE_LIMIT_TURNS_PER_MINUTE (and fail-open on Redis down)
- 503 when the CapacityLimiter is saturated
"""

import asyncio
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt

from app.core.capacity import CapacityLimiter
from app.core.deps import (
    get_agent_service,
    get_decision_engine_service,
    get_groq_client,
    get_lesson_repository,
    get_module_repository,
    get_rate_limiter,
    get_redis_repository,
    get_tts_service,
)
from app.core.rate_limit import RateLimiter
from app.main import app
from app.schemas.domain import StepState

# Constants

TEST_SECRET = "test-secret-only-for-pytest-never-use-in-prod!"
TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_LESSON_ID = "lesson-001"

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


def _post_turn(client: TestClient, audio: bytes = b"RIFF-fake-audio") -> object:
    return client.post(
        "/v1/conversation/turn",
        headers=_auth_headers(),
        files={"audio_file": ("audio.webm", BytesIO(audio), "audio/webm")},
        data={"lesson_id": TEST_LESSON_ID},
    )


class _FakeRedisCounter:
    """Minimal in-memory INCR/EXPIRE, enough for the fixed-window limiter."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True


class _BrokenRedis:
    async def incr(self, key: str) -> int:
        raise ConnectionError("Redis down")

    async def expire(self, key: str, seconds: int) -> bool:
        raise ConnectionError("Redis down")


# Fixtures


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    return TestClient(app, raise_server_exceptions=False)


@contextmanager
def _override_turn_deps(
    rate_limiter: RateLimiter | MagicMock | None = None,
) -> Generator[None, None, None]:
    """Happy-path mocks for every external service /turn touches."""
    groq = MagicMock()
    transcription = MagicMock()
    transcription.text = "hola"
    groq.audio.transcriptions.create.return_value = transcription

    lesson_repo = MagicMock()
    lesson_repo.get_lesson = AsyncMock(return_value={"titulo": "Test"})

    agent = MagicMock()
    agent.generate_response = AsyncMock(
        return_value=("ok!", {"paso_aplicado": "4", "error_detectado": None})
    )

    tts = MagicMock()
    tts.synthesize = AsyncMock(return_value=None)

    redis_repo = MagicMock()
    redis_repo.get_history = AsyncMock(return_value=[])
    redis_repo.append_turn = AsyncMock(return_value=None)

    engine = MagicMock()
    engine.get_current_state = AsyncMock(
        return_value=StepState(
            current_step=1, turns_on_step=0, consecutive_errors=0, completed=False
        )
    )
    engine.update_after_turn = AsyncMock(
        return_value=StepState(
            current_step=1, turns_on_step=1, consecutive_errors=0, completed=False
        )
    )
    engine.get_step_context = MagicMock(return_value="Current step: 1/6.")

    module_repo = MagicMock()
    module_repo.get_next_lesson_id = AsyncMock(return_value=None)

    if rate_limiter is None:
        rate_limiter = MagicMock()
        rate_limiter.check = AsyncMock(return_value=None)

    app.dependency_overrides[get_groq_client] = lambda: groq
    app.dependency_overrides[get_lesson_repository] = lambda: lesson_repo
    app.dependency_overrides[get_agent_service] = lambda: agent
    app.dependency_overrides[get_tts_service] = lambda: tts
    app.dependency_overrides[get_redis_repository] = lambda: redis_repo
    app.dependency_overrides[get_decision_engine_service] = lambda: engine
    app.dependency_overrides[get_module_repository] = lambda: module_repo
    app.dependency_overrides[get_rate_limiter] = lambda: rate_limiter
    try:
        yield
    finally:
        app.dependency_overrides.clear()


# Tests: audio size limit (413)


def test_audio_above_limit_returns_413(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "MAX_AUDIO_BYTES", 10)
    with _override_turn_deps():
        response = _post_turn(client, audio=b"x" * 11)

    assert response.status_code == 413  # type: ignore[attr-defined]


def test_audio_within_limit_returns_200(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "MAX_AUDIO_BYTES", 1024)
    with _override_turn_deps():
        response = _post_turn(client, audio=b"x" * 100)

    assert response.status_code == 200  # type: ignore[attr-defined]


# Tests: per-user rate limit (429)


def test_rate_limit_exceeded_returns_429(client: TestClient) -> None:
    limiter = RateLimiter(_FakeRedisCounter(), limit_per_minute=2)  # type: ignore[arg-type]
    with _override_turn_deps(rate_limiter=limiter):
        first = _post_turn(client)
        second = _post_turn(client)
        third = _post_turn(client)

    assert first.status_code == 200  # type: ignore[attr-defined]
    assert second.status_code == 200  # type: ignore[attr-defined]
    assert third.status_code == 429  # type: ignore[attr-defined]


def test_rate_limit_fails_open_when_redis_down(client: TestClient) -> None:
    """Redis down must NOT block students -- limiter fails open."""
    limiter = RateLimiter(_BrokenRedis(), limit_per_minute=1)  # type: ignore[arg-type]
    with _override_turn_deps(rate_limiter=limiter):
        first = _post_turn(client)
        second = _post_turn(client)

    assert first.status_code == 200  # type: ignore[attr-defined]
    assert second.status_code == 200  # type: ignore[attr-defined]


# Tests: capacity limiter (503)


@pytest.mark.asyncio
async def test_capacity_limiter_rejects_when_saturated() -> None:
    limiter = CapacityLimiter(max_concurrent=1, wait_timeout=0.05)

    async with limiter:
        with pytest.raises(HTTPException) as exc_info:
            async with limiter:
                pass  # pragma: no cover

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_capacity_limiter_releases_slot() -> None:
    limiter = CapacityLimiter(max_concurrent=1, wait_timeout=0.05)

    async with limiter:
        pass
    # Slot released -- second acquisition must succeed
    async with limiter:
        pass


@pytest.mark.asyncio
async def test_capacity_limiter_allows_queued_waiter() -> None:
    """A waiter within wait_timeout gets the slot when it frees up."""
    limiter = CapacityLimiter(max_concurrent=1, wait_timeout=1.0)
    results: list[str] = []

    async def hold_and_release() -> None:
        async with limiter:
            results.append("first")
            await asyncio.sleep(0.05)

    async def wait_for_slot() -> None:
        await asyncio.sleep(0.01)  # ensure the first task grabs the slot
        async with limiter:
            results.append("second")

    await asyncio.gather(hold_and_release(), wait_for_slot())
    assert results == ["first", "second"]
