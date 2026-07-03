"""
Integration tests: GET /v1/progress/lesson/{lesson_id} and /v1/progress/module/{module_id}
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

# ── Constants ─────────────────────────────────────────────────────────────────

TEST_SECRET = "test-secret-only-for-pytest-never-use-in-prod!"
TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_EMAIL = "ilya@kotoba.test"
TEST_LESSON_ID = "lesson-001"
TEST_LESSON_ID_2 = "lesson-002"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_token(
    *,
    secret: str = TEST_SECRET,
    user_id: str = TEST_USER_ID,
    email: str = TEST_EMAIL,
) -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    return jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "role": "authenticated",
            "aud": "authenticated",
            "iat": now,
            "exp": now + 3600,
        },
        secret,
        algorithm="HS256",
    )


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_make_token()}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    return TestClient(app, raise_server_exceptions=False)


def _mock_engine(*, step: int, turns: int, errors: int = 0, completed: bool = False) -> MagicMock:
    engine = MagicMock()
    engine.get_current_state = AsyncMock(
        return_value={
            "current_step": step,
            "turns_on_step": turns,
            "consecutive_errors": errors,
            "completed": completed,
        }
    )
    return engine


@contextmanager
def _override_lesson(engine: MagicMock) -> Generator[None, None, None]:
    app.dependency_overrides[get_decision_engine_service] = lambda: engine
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@contextmanager
def _override_module(
    module_repo: MagicMock, progress_repo: MagicMock
) -> Generator[None, None, None]:
    app.dependency_overrides[get_module_repository] = lambda: module_repo
    app.dependency_overrides[get_student_progress_repository] = lambda: progress_repo
    try:
        yield
    finally:
        app.dependency_overrides.clear()


# ── Lesson endpoint tests ─────────────────────────────────────────────────────


def test_lesson_progress_not_started(client: TestClient) -> None:
    """Step 1, turns 0 -> status not_started."""
    with _override_lesson(_mock_engine(step=1, turns=0)):
        r = client.get(f"/v1/progress/lesson/{TEST_LESSON_ID}", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_started"
    assert body["current_step"] == 1
    assert body["lesson_id"] == TEST_LESSON_ID


def test_lesson_progress_in_progress(client: TestClient) -> None:
    """Step 3, turns 1 -> status in_progress."""
    with _override_lesson(_mock_engine(step=3, turns=1)):
        r = client.get(f"/v1/progress/lesson/{TEST_LESSON_ID}", headers=_auth_headers())
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"
    assert r.json()["current_step"] == 3


def test_lesson_progress_completed(client: TestClient) -> None:
    """completed=True -> status completed."""
    with _override_lesson(_mock_engine(step=6, turns=0, completed=True)):
        r = client.get(f"/v1/progress/lesson/{TEST_LESSON_ID}", headers=_auth_headers())
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_lesson_progress_requires_auth(client: TestClient) -> None:
    """No JWT -> 401."""
    r = client.get(f"/v1/progress/lesson/{TEST_LESSON_ID}")
    assert r.status_code == 401


# ── Module endpoint tests ─────────────────────────────────────────────────────


def test_module_progress_no_prior_activity(client: TestClient) -> None:
    """Module with 2 lessons, no prior activity -> both not_started."""
    module_repo = MagicMock()
    module_repo.get_lesson_ids = AsyncMock(return_value=[TEST_LESSON_ID, TEST_LESSON_ID_2])

    progress_repo = MagicMock()
    progress_repo.get_progress = AsyncMock(return_value=None)

    with _override_module(module_repo, progress_repo):
        r = client.get("/v1/progress/module/module-001", headers=_auth_headers())

    assert r.status_code == 200
    lessons = r.json()["lessons"]
    assert len(lessons) == 2
    assert all(l["status"] == "not_started" for l in lessons)


def test_module_progress_partial(client: TestClient) -> None:
    """First lesson in_progress, second not started."""
    module_repo = MagicMock()
    module_repo.get_lesson_ids = AsyncMock(return_value=[TEST_LESSON_ID, TEST_LESSON_ID_2])

    def _progress_side_effect(user_id: str, lesson_id: str):
        if lesson_id == TEST_LESSON_ID:
            return {"current_step": 3, "status": "in_progress"}
        return None

    progress_repo = MagicMock()
    progress_repo.get_progress = AsyncMock(side_effect=_progress_side_effect)

    with _override_module(module_repo, progress_repo):
        r = client.get("/v1/progress/module/module-001", headers=_auth_headers())

    assert r.status_code == 200
    lessons = r.json()["lessons"]
    assert lessons[0]["status"] == "in_progress"
    assert lessons[0]["current_step"] == 3
    assert lessons[1]["status"] == "not_started"


def test_module_progress_empty_module(client: TestClient) -> None:
    """Module with no lessons -> empty list."""
    module_repo = MagicMock()
    module_repo.get_lesson_ids = AsyncMock(return_value=[])

    progress_repo = MagicMock()
    progress_repo.get_progress = AsyncMock(return_value=None)

    with _override_module(module_repo, progress_repo):
        r = client.get("/v1/progress/module/module-empty", headers=_auth_headers())

    assert r.status_code == 200
    assert r.json()["lessons"] == []


def test_module_progress_requires_auth(client: TestClient) -> None:
    """No JWT -> 401."""
    r = client.get("/v1/progress/module/module-001")
    assert r.status_code == 401
