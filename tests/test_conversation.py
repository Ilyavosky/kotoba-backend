"""
Integration tests: POST /v1/conversation/turn
"""

import io
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.core.deps import (
    get_agent_service,
    get_groq_client,
    get_lesson_repository,
    get_redis_repository,
    get_tts_service,
)
from app.main import app

# ── Constants ─────────────────────────────────────────────────────────────────

TEST_SECRET = "test-secret-only-for-pytest-never-use-in-prod!"
TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_EMAIL = "ilya@kotoba.test"
TEST_LESSON_ID = "lesson-001"
TEST_INTERVENCION = "Good try! Can you say it again?"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_token(
    *,
    secret: str = TEST_SECRET,
    user_id: str = TEST_USER_ID,
    email: str = TEST_EMAIL,
    audience: str = "authenticated",
    exp_offset: int = 3600,
) -> str:
    now = int(datetime.now(UTC).timestamp())
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


def _auth_headers(token: str | None = None) -> dict:
    t = token or _make_token()
    return {"Authorization": f"Bearer {t}"}


def _fake_audio() -> bytes:
    return b"RIFF\x00\x00\x00\x00WAVEfmt "


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def mock_groq_success() -> MagicMock:
    groq = MagicMock()
    transcription_result = MagicMock()
    transcription_result.text = "hola, ¿cómo estás?"
    groq.audio.transcriptions.create.return_value = transcription_result
    return groq


@pytest.fixture()
def mock_groq_asr_failure() -> MagicMock:
    groq = MagicMock()
    groq.audio.transcriptions.create.side_effect = Exception("Groq ASR unavailable")
    return groq


@pytest.fixture()
def mock_lesson_repository() -> MagicMock:
    repo = MagicMock()
    repo.get_lesson = AsyncMock(return_value={"metadata": {"title": "Test Lesson"}})
    return repo


@pytest.fixture()
def mock_agent_service() -> MagicMock:
    agent = MagicMock()
    agent.generate_response = AsyncMock(
        return_value=(TEST_INTERVENCION, {"paso_aplicado": 4})
    )
    return agent


@pytest.fixture()
def mock_tts_service() -> MagicMock:
    tts = MagicMock()
    tts.synthesize = AsyncMock(return_value="https://supabase.test/audio.mp3")
    return tts


@pytest.fixture()
def mock_redis_repository() -> MagicMock:
    repo = MagicMock()
    repo.get_history = AsyncMock(return_value=[])
    repo.append_turn = AsyncMock(return_value=None)
    return repo


@pytest.fixture()
def mock_redis_repository_failure() -> MagicMock:
    repo = MagicMock()
    repo.get_history = AsyncMock(side_effect=Exception("Redis unavailable"))
    repo.append_turn = AsyncMock(return_value=None)
    return repo


@contextmanager
def _override_all(
    mock_groq: MagicMock,
    mock_lesson: MagicMock,
    mock_agent: MagicMock,
    mock_tts: MagicMock,
    mock_redis: MagicMock,
) -> Generator[None, None, None]:
    app.dependency_overrides[get_groq_client] = lambda: mock_groq
    app.dependency_overrides[get_lesson_repository] = lambda: mock_lesson
    app.dependency_overrides[get_agent_service] = lambda: mock_agent
    app.dependency_overrides[get_tts_service] = lambda: mock_tts
    app.dependency_overrides[get_redis_repository] = lambda: mock_redis
    try:
        yield
    finally:
        app.dependency_overrides.clear()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_conversation_turn_success(
    client: TestClient,
    mock_groq_success: MagicMock,
    mock_lesson_repository: MagicMock,
    mock_agent_service: MagicMock,
    mock_tts_service: MagicMock,
    mock_redis_repository: MagicMock,
) -> None:
    """Happy path: valid audio + valid JWT → 200 with expected JSON fields."""
    with _override_all(
        mock_groq_success,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository,
    ):
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={"audio_file": (
                "audio.webm", io.BytesIO(_fake_audio()), "audio/webm"
            )},  # noqa: E501
            data={"lesson_id": TEST_LESSON_ID},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["transcription"] == "hola, ¿cómo estás?"
    assert body["agent_response"] == TEST_INTERVENCION
    assert body["audio_url"] == "https://supabase.test/audio.mp3"


def test_conversation_turn_requires_auth(client: TestClient) -> None:
    """No Authorization header → 401 before even reaching the service."""
    response = client.post(
        "/v1/conversation/turn",
        files={"audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")},  # noqa: E501
        data={"lesson_id": TEST_LESSON_ID},
    )
    assert response.status_code == 401


def test_conversation_turn_asr_failure_returns_502(
    client: TestClient,
    mock_groq_asr_failure: MagicMock,
    mock_lesson_repository: MagicMock,
    mock_agent_service: MagicMock,
    mock_tts_service: MagicMock,
    mock_redis_repository: MagicMock,
) -> None:
    """ASR stage raises → endpoint must return 502, not 500."""
    with _override_all(
        mock_groq_asr_failure,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository,
    ):
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={"audio_file": (
                "audio.webm", io.BytesIO(_fake_audio()), "audio/webm"
            )},  # noqa: E501
            data={"lesson_id": TEST_LESSON_ID},
        )

    assert response.status_code == 502


def test_conversation_turn_saves_to_redis(
    client: TestClient,
    mock_groq_success: MagicMock,
    mock_lesson_repository: MagicMock,
    mock_agent_service: MagicMock,
    mock_tts_service: MagicMock,
    mock_redis_repository: MagicMock,
) -> None:
    """Successful turn → append_turn called with correct args."""
    with _override_all(
        mock_groq_success,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository,
    ):
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={"audio_file": (
                "audio.webm", io.BytesIO(_fake_audio()), "audio/webm"
            )},  # noqa: E501
            data={"lesson_id": TEST_LESSON_ID},
        )

    assert response.status_code == 200
    mock_redis_repository.append_turn.assert_called_once_with(
        TEST_USER_ID,
        TEST_LESSON_ID,
        "hola, ¿cómo estás?",
        TEST_INTERVENCION,
    )


def test_conversation_turn_redis_failure_returns_200(
    client: TestClient,
    mock_groq_success: MagicMock,
    mock_lesson_repository: MagicMock,
    mock_agent_service: MagicMock,
    mock_tts_service: MagicMock,
    mock_redis_repository_failure: MagicMock,
) -> None:
    """Redis unavailable → endpoint still returns 200 with empty context fallback."""
    with _override_all(
        mock_groq_success,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository_failure,
    ):
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={"audio_file": (
                "audio.webm", io.BytesIO(_fake_audio()), "audio/webm"
            )},  # noqa: E501
            data={"lesson_id": TEST_LESSON_ID},
        )

    assert response.status_code == 200
