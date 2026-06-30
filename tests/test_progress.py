"""
Integration tests: GET /v1/progress/lesson/{lesson_id}
              and GET /v1/progress/module/{module_id}
"""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.core.deps import (
    get_decision_engine_service,
    get_module_repository,
    get_student_progress_repository,
)
from app.main import app
from app.schemas.domain import StepState

# Constants

TEST_SECRET = "test-secret-only-for-pytest-never-use-in-prod!"
TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_EMAIL = "ilya@kotoba.test"
TEST_LESSON_ID = "lesson-001"
TEST_LESSON_ID_2 = "lesson-002"
TEST_MODULE_ID = "module-001"

# Helpers


def _make_token(
    *,
    secret: str = TEST_SECRET,
    user_id: str = TEST_USER_ID,
    email: str = TEST_EMAIL,
    audience: str = "authenticated",
    exp_offset: int = 3600,
) -> str:
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


def _auth_headers(token: str | None = None) -> dict:
    t = token or _make_token()
    return {"Authorization": f"Bearer {t}"}


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
def mock_decision_engine_not_started() -> MagicMock:
    """User has never touched this lesson."""
    engine = MagicMock()
    engine.get_current_state = AsyncMock(return_value=_make_step_state())
    return engine


@pytest.fixture()
def mock_decision_engine_in_progress() -> MagicMock:
    """User is on step 3, 1 turn done on that step."""
    engine = MagicMock()
    engine.get_current_state = AsyncMock(
        return_value=_make_step_state(current_step=3, turns_on_step=1)
    )
    return engine


@pytest.fixture()
def mock_decision_engine_completed() -> MagicMock:
    """User has completed the lesson."""
    engine = MagicMock()
    engine.get_current_state = AsyncMock(
        return_value=_make_step_state(current_step=6, turns_on_step=2, completed=True)
    )
    return engine


@pytest.fixture()
def mock_module_repository_with_lessons() -> MagicMock:
    """Module contains two lessons."""
    repo = MagicMock()
    repo.get_lesson_ids = AsyncMock(return_value=[TEST_LESSON_ID, TEST_LESSON_ID_2])
    return repo


@pytest.fixture()
def mock_module_repository_empty() -> MagicMock:
    """Module does not exist or has no lessons."""
    repo = MagicMock()
    repo.get_lesson_ids = AsyncMock(return_value=[])
    return repo


@pytest.fixture()
def mock_progress_repo_no_progress() -> MagicMock:
    """No progress recorded for any lesson."""
    repo = MagicMock()
    repo.get_progress = AsyncMock(return_value=None)
    return repo


@pytest.fixture()
def mock_progress_repo_with_progress() -> MagicMock:
    """First lesson in progress, second not started."""
    repo = MagicMock()

    async def _get_progress(user_id: str, lesson_id: str) -> dict | None:
        if lesson_id == TEST_LESSON_ID:
            return {"current_step": 3, "status": "in_progress"}
        return None

    repo.get_progress = AsyncMock(side_effect=_get_progress)
    return repo


@contextmanager
def _override_lesson(
    mock_engine: MagicMock,
) -> Generator[None, None, None]:
    app.dependency_overrides[get_decision_engine_service] = lambda: mock_engine
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@contextmanager
def _override_module(
    mock_module: MagicMock,
    mock_progress: MagicMock,
) -> Generator[None, None, None]:
    app.dependency_overrides[get_module_repository] = lambda: mock_module
    app.dependency_overrides[get_student_progress_repository] = lambda: mock_progress
    try:
        yield
    finally:
        app.dependency_overrides.clear()


# Tests: GET /v1/progress/lesson/{lesson_id}


def test_lesson_progress_not_started(
    client: TestClient,
    mock_decision_engine_not_started: MagicMock,
) -> None:
    """User with no prior activity -> step 1, not_started."""
    with _override_lesson(mock_decision_engine_not_started):
        response = client.get(
            f"/v1/progress/lesson/{TEST_LESSON_ID}",
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["lesson_id"] == TEST_LESSON_ID
    assert body["current_step"] == 1
    assert body["status"] == "not_started"
    assert body["turns_on_step"] == 0
    assert body["consecutive_errors"] == 0


def test_lesson_progress_in_progress(
    client: TestClient,
    mock_decision_engine_in_progress: MagicMock,
) -> None:
    """User on step 3 -> in_progress."""
    with _override_lesson(mock_decision_engine_in_progress):
        response = client.get(
            f"/v1/progress/lesson/{TEST_LESSON_ID}",
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["current_step"] == 3
    assert body["status"] == "in_progress"


def test_lesson_progress_completed(
    client: TestClient,
    mock_decision_engine_completed: MagicMock,
) -> None:
    """Completed lesson -> status completed."""
    with _override_lesson(mock_decision_engine_completed):
        response = client.get(
            f"/v1/progress/lesson/{TEST_LESSON_ID}",
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["current_step"] == 6


def test_lesson_progress_requires_auth(client: TestClient) -> None:
    """No JWT -> 401."""
    response = client.get(f"/v1/progress/lesson/{TEST_LESSON_ID}")
    assert response.status_code == 401


# Tests: GET /v1/progress/module/{module_id}


def test_module_progress_no_prior_activity(
    client: TestClient,
    mock_module_repository_with_lessons: MagicMock,
    mock_progress_repo_no_progress: MagicMock,
) -> None:
    """Module with 2 lessons, user has never started -> both not_started at step 1."""
    with _override_module(mock_module_repository_with_lessons, mock_progress_repo_no_progress):
        response = client.get(
            f"/v1/progress/module/{TEST_MODULE_ID}",
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["lessons"]) == 2
    for lesson in body["lessons"]:
        assert lesson["current_step"] == 1
        assert lesson["status"] == "not_started"


def test_module_progress_partial(
    client: TestClient,
    mock_module_repository_with_lessons: MagicMock,
    mock_progress_repo_with_progress: MagicMock,
) -> None:
    """First lesson in progress, second not started."""
    with _override_module(mock_module_repository_with_lessons, mock_progress_repo_with_progress):
        response = client.get(
            f"/v1/progress/module/{TEST_MODULE_ID}",
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    lessons = response.json()["lessons"]
    assert lessons[0]["lesson_id"] == TEST_LESSON_ID
    assert lessons[0]["current_step"] == 3
    assert lessons[0]["status"] == "in_progress"
    assert lessons[1]["lesson_id"] == TEST_LESSON_ID_2
    assert lessons[1]["status"] == "not_started"


def test_module_progress_empty_module(
    client: TestClient,
    mock_module_repository_empty: MagicMock,
    mock_progress_repo_no_progress: MagicMock,
) -> None:
    """Module not found or no lessons -> empty list."""
    with _override_module(mock_module_repository_empty, mock_progress_repo_no_progress):
        response = client.get(
            f"/v1/progress/module/{TEST_MODULE_ID}",
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    assert response.json()["lessons"] == []


def test_module_progress_requires_auth(client: TestClient) -> None:
    """No JWT -> 401."""
    response = client.get(f"/v1/progress/module/{TEST_MODULE_ID}")
    assert response.status_code == 401