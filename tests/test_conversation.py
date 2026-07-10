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
    get_decision_engine_service,
    get_groq_client,
    get_lesson_repository,
    get_module_repository,
    get_rate_limiter,
    get_redis_repository,
    get_tts_service,
)
from app.main import app
from app.schemas.domain import StepState

# Constants

TEST_SECRET = "test-secret-only-for-pytest-never-use-in-prod!"
TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_EMAIL = "ilya@kotoba.test"
TEST_LESSON_ID = "lesson-001"
TEST_NEXT_LESSON_ID = "lesson-002"
TEST_INTERVENCION = "Good try! Can you say it again?"

# Helpers


def _make_token(
    *,
    secret: str = TEST_SECRET,
    user_id: str = TEST_USER_ID,
    email: str = TEST_EMAIL,
    audience: str = "authenticated",
    exp_offset: int = 3600,
) -> str:
    now = int(datetime.now(UTC).timestamp())
    return str(jwt.encode(
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
    ))


def _auth_headers(token: str | None = None) -> dict:
    t = token or _make_token()
    return {"Authorization": f"Bearer {t}"}


def _fake_audio() -> bytes:
    return b"RIFF\x00\x00\x00\x00WAVEfmt "


def _make_step_state(
    *,
    current_step: int = 1,
    turns_on_step: int = 0,
    consecutive_errors: int = 0,
    completed: bool = False,
) -> StepState:
    return StepState(
        current_step=current_step,
        turns_on_step=turns_on_step,
        consecutive_errors=consecutive_errors,
        completed=completed,
    )


# Fixtures


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def mock_groq_success() -> MagicMock:
    groq = MagicMock()
    transcription_result = MagicMock()
    transcription_result.text = "hola, como estas?"
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
        return_value=(
            TEST_INTERVENCION,
            {"paso_aplicado": "4", "error_detectado": None},
        )
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


@pytest.fixture()
def mock_decision_engine() -> MagicMock:
    """Decision engine: lesson in progress, step 1."""
    engine = MagicMock()
    in_progress_state = _make_step_state(current_step=1, turns_on_step=1)
    engine.get_current_state = AsyncMock(return_value=_make_step_state())
    engine.update_after_turn = AsyncMock(return_value=in_progress_state)
    engine.get_step_context = MagicMock(
        return_value="Current step: 1/6. Turns on step: 0. Consecutive errors: 0."
    )
    return engine


@pytest.fixture()
def mock_decision_engine_completes_lesson() -> MagicMock:
    """Decision engine: this turn completes step 6."""
    engine = MagicMock()
    completed_state = _make_step_state(current_step=6, turns_on_step=2, completed=True)
    engine.get_current_state = AsyncMock(
        return_value=_make_step_state(current_step=6, turns_on_step=1)
    )
    engine.update_after_turn = AsyncMock(return_value=completed_state)
    engine.get_step_context = MagicMock(
        return_value="Current step: 6/6. Turns on step: 1. Consecutive errors: 0."
    )
    return engine


@pytest.fixture()
def mock_module_repository() -> MagicMock:
    """Module repo: lesson-001 has a next lesson (lesson-002)."""
    repo = MagicMock()
    repo.get_next_lesson_id = AsyncMock(return_value=TEST_NEXT_LESSON_ID)
    return repo


@pytest.fixture()
def mock_module_repository_last_lesson() -> MagicMock:
    """Module repo: current lesson is the last one in the module."""
    repo = MagicMock()
    repo.get_next_lesson_id = AsyncMock(return_value=None)
    return repo


@contextmanager
def _override_all(
    mock_groq: MagicMock,
    mock_lesson: MagicMock,
    mock_agent: MagicMock,
    mock_tts: MagicMock,
    mock_redis: MagicMock,
    mock_engine: MagicMock,
    mock_module: MagicMock,
) -> Generator[None, None, None]:
    app.dependency_overrides[get_groq_client] = lambda: mock_groq
    app.dependency_overrides[get_lesson_repository] = lambda: mock_lesson
    app.dependency_overrides[get_agent_service] = lambda: mock_agent
    app.dependency_overrides[get_tts_service] = lambda: mock_tts
    app.dependency_overrides[get_redis_repository] = lambda: mock_redis
    app.dependency_overrides[get_decision_engine_service] = lambda: mock_engine
    app.dependency_overrides[get_module_repository] = lambda: mock_module
    # Permissive rate limiter -- keeps unit tests off the real Redis client
    permissive_limiter = MagicMock()
    permissive_limiter.check = AsyncMock(return_value=None)
    app.dependency_overrides[get_rate_limiter] = lambda: permissive_limiter
    try:
        yield
    finally:
        app.dependency_overrides.clear()


# Tests


def test_conversation_turn_success(
    client: TestClient,
    mock_groq_success: MagicMock,
    mock_lesson_repository: MagicMock,
    mock_agent_service: MagicMock,
    mock_tts_service: MagicMock,
    mock_redis_repository: MagicMock,
    mock_decision_engine: MagicMock,
    mock_module_repository: MagicMock,
) -> None:
    """Happy path: valid audio + valid JWT -> 200 with expected JSON fields."""
    with _override_all(
        mock_groq_success,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository,
        mock_decision_engine,
        mock_module_repository,
    ):
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={
                "audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")
            },
            data={"lesson_id": TEST_LESSON_ID},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["transcription"] == "hola, como estas?"
    assert body["agent_response"] == TEST_INTERVENCION
    assert body["audio_url"] == "https://supabase.test/audio.mp3"


def test_conversation_turn_requires_auth(client: TestClient) -> None:
    """No Authorization header -> 401 before reaching the service."""
    response = client.post(
        "/v1/conversation/turn",
        files={"audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")},
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
    mock_decision_engine: MagicMock,
    mock_module_repository: MagicMock,
) -> None:
    """ASR stage raises -> endpoint must return 502, not 500."""
    with _override_all(
        mock_groq_asr_failure,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository,
        mock_decision_engine,
        mock_module_repository,
    ):
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={
                "audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")
            },
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
    mock_decision_engine: MagicMock,
    mock_module_repository: MagicMock,
) -> None:
    """Successful turn -> append_turn called with correct args."""
    with _override_all(
        mock_groq_success,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository,
        mock_decision_engine,
        mock_module_repository,
    ):
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={
                "audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")
            },
            data={"lesson_id": TEST_LESSON_ID},
        )

    assert response.status_code == 200
    mock_redis_repository.append_turn.assert_called_once_with(
        TEST_USER_ID,
        TEST_LESSON_ID,
        "hola, como estas?",
        TEST_INTERVENCION,
    )


def test_conversation_turn_redis_failure_returns_200(
    client: TestClient,
    mock_groq_success: MagicMock,
    mock_lesson_repository: MagicMock,
    mock_agent_service: MagicMock,
    mock_tts_service: MagicMock,
    mock_redis_repository_failure: MagicMock,
    mock_decision_engine: MagicMock,
    mock_module_repository: MagicMock,
) -> None:
    """Redis unavailable -> endpoint still returns 200 with empty context fallback."""
    with _override_all(
        mock_groq_success,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository_failure,
        mock_decision_engine,
        mock_module_repository,
    ):
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={
                "audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")
            },
            data={"lesson_id": TEST_LESSON_ID},
        )

    assert response.status_code == 200


# K-06.1: Student model (decision engine integration)


def test_turn_in_progress_lesson_completed_false(
    client: TestClient,
    mock_groq_success: MagicMock,
    mock_lesson_repository: MagicMock,
    mock_agent_service: MagicMock,
    mock_tts_service: MagicMock,
    mock_redis_repository: MagicMock,
    mock_decision_engine: MagicMock,
    mock_module_repository: MagicMock,
) -> None:
    """Mid-lesson turn -> lesson_completed is False, next_lesson_id is None."""
    with _override_all(
        mock_groq_success,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository,
        mock_decision_engine,
        mock_module_repository,
    ):
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={
                "audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")
            },
            data={"lesson_id": TEST_LESSON_ID},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["lesson_completed"] is False
    assert body["next_lesson_id"] is None


def test_decision_engine_called_with_correct_args(
    client: TestClient,
    mock_groq_success: MagicMock,
    mock_lesson_repository: MagicMock,
    mock_agent_service: MagicMock,
    mock_tts_service: MagicMock,
    mock_redis_repository: MagicMock,
    mock_decision_engine: MagicMock,
    mock_module_repository: MagicMock,
) -> None:
    """Decision engine receives correct user_id and lesson_id on each turn."""
    with _override_all(
        mock_groq_success,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository,
        mock_decision_engine,
        mock_module_repository,
    ):
        client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={
                "audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")
            },
            data={"lesson_id": TEST_LESSON_ID},
        )

    mock_decision_engine.get_current_state.assert_called_once_with(
        TEST_USER_ID, TEST_LESSON_ID
    )
    mock_decision_engine.update_after_turn.assert_called_once()
    call_args = mock_decision_engine.update_after_turn.call_args[0]
    assert call_args[0] == TEST_USER_ID
    assert call_args[1] == TEST_LESSON_ID


# K-05.2: Multi-lesson module progression


def test_lesson_completion_sets_lesson_completed_true(
    client: TestClient,
    mock_groq_success: MagicMock,
    mock_lesson_repository: MagicMock,
    mock_agent_service: MagicMock,
    mock_tts_service: MagicMock,
    mock_redis_repository: MagicMock,
    mock_decision_engine_completes_lesson: MagicMock,
    mock_module_repository: MagicMock,
) -> None:
    """Turn that completes step 6 -> lesson_completed True, next_lesson_id populated."""
    with _override_all(
        mock_groq_success,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository,
        mock_decision_engine_completes_lesson,
        mock_module_repository,
    ):
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={
                "audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")
            },
            data={"lesson_id": TEST_LESSON_ID},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["lesson_completed"] is True
    assert body["next_lesson_id"] == TEST_NEXT_LESSON_ID


def test_lesson_completion_last_in_module_returns_null_next(
    client: TestClient,
    mock_groq_success: MagicMock,
    mock_lesson_repository: MagicMock,
    mock_agent_service: MagicMock,
    mock_tts_service: MagicMock,
    mock_redis_repository: MagicMock,
    mock_decision_engine_completes_lesson: MagicMock,
    mock_module_repository_last_lesson: MagicMock,
) -> None:
    """Lesson completes but it is the last in its module -> next_lesson_id is None."""
    with _override_all(
        mock_groq_success,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository,
        mock_decision_engine_completes_lesson,
        mock_module_repository_last_lesson,
    ):
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={
                "audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")
            },
            data={"lesson_id": TEST_LESSON_ID},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["lesson_completed"] is True
    assert body["next_lesson_id"] is None


def test_module_repository_not_called_when_lesson_not_completed(
    client: TestClient,
    mock_groq_success: MagicMock,
    mock_lesson_repository: MagicMock,
    mock_agent_service: MagicMock,
    mock_tts_service: MagicMock,
    mock_redis_repository: MagicMock,
    mock_decision_engine: MagicMock,
    mock_module_repository: MagicMock,
) -> None:
    """Module repo is NOT queried when the lesson is still in progress."""
    with _override_all(
        mock_groq_success,
        mock_lesson_repository,
        mock_agent_service,
        mock_tts_service,
        mock_redis_repository,
        mock_decision_engine,
        mock_module_repository,
    ):
        client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={
                "audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")
            },
            data={"lesson_id": TEST_LESSON_ID},
        )

    mock_module_repository.get_next_lesson_id.assert_not_called()
