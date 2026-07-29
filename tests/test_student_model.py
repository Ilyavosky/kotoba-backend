"""
1. Unit: BKT update formulas (research doc, section 2.5)
2. Unit: error classification (section 2.3)
3. Unit: StudentModelService.update_after_turn
4. Unit: StudentModelRepository Redis <-> Supabase fallback
5. Integration: GET /v1/progress/lesson/{lesson_id}/student-model
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.core.deps import get_student_model_service
from app.main import app
from app.repositories.student_model_repository import StudentModelRepository
from app.schemas.domain import AgentReasoning
from app.schemas.student_model import BktState, ErrorPatterns, StudentModel
from app.services.student_model_service import (
    StudentModelService,
    bkt_update,
    classify_error,
    create_default_model,
    get_mastery_level,
)


TEST_SECRET = "test-secret-only-for-pytest-never-use-in-prod!"
TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_EMAIL = "ilya@kotoba.test"
TEST_LESSON_ID = "lesson-001"



def _make_token() -> str:
    now = int(datetime.now(UTC).timestamp())
    return str(
        jwt.encode(
            {
                "sub": TEST_USER_ID,
                "email": TEST_EMAIL,
                "role": "authenticated",
                "aud": "authenticated",
                "iat": now,
                "exp": now + 3600,
            },
            TEST_SECRET,
            algorithm="HS256",
        )
    )


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_make_token()}"}


def _reasoning(
    error: str | None = None,
    categoria: str | None = None,
    vocab: list[str] | None = None,
) -> AgentReasoning:
    r: AgentReasoning = {"paso_aplicado": "4"}
    if error is not None:
        r["error_detectado"] = error
    if categoria is not None:
        r["categoria_error"] = categoria
    if vocab is not None:
        r["vocabulario_activado"] = vocab
    return r


def _make_service(
    existing_model: StudentModel | None = None,
) -> tuple[StudentModelService, MagicMock]:
    repo = MagicMock()
    repo.get_model = AsyncMock(return_value=existing_model)
    repo.save_model = AsyncMock(return_value=None)
    return StudentModelService(repo), repo


# 1. BKT unit tests


def test_bkt_correct_answer_increases_p_learned() -> None:
    assert bkt_update(0.2, correct=True) > 0.2


def test_bkt_incorrect_answer_decreases_posterior_below_transition() -> None:
    assert bkt_update(0.5, correct=False) < bkt_update(0.5, correct=True)


def test_bkt_stays_within_bounds() -> None:
    for p in (0.0, 0.01, 0.5, 0.99, 1.0):
        for correct in (True, False):
            assert 0.0 <= bkt_update(p, correct) <= 1.0


def test_bkt_reaches_mastery_with_consecutive_correct_answers() -> None:
    p = 0.2
    for _ in range(20):
        p = bkt_update(p, correct=True)
    assert p >= 0.95
    assert get_mastery_level(p) == "mastered"


def test_mastery_levels_match_research_thresholds() -> None:
    assert get_mastery_level(0.2) == "introducing"
    assert get_mastery_level(0.5) == "practicing"
    assert get_mastery_level(0.94) == "practicing"
    assert get_mastery_level(0.95) == "mastered"


# 2. Error classification unit tests


def test_classify_returns_none_without_error() -> None:
    assert classify_error(_reasoning()) is None
    assert classify_error(_reasoning(error=None, vocab=["ticket"])) is None


def test_classify_prefers_explicit_spanish_category() -> None:
    r = _reasoning(error="uso incorrecto", categoria="gramatica")
    assert classify_error(r) == "grammar"
    r = _reasoning(error="fonema mal pronunciado", categoria="pronunciación")
    assert classify_error(r) == "pronunciation"
    r = _reasoning(error="palabra equivocada", categoria="vocabulario")
    assert classify_error(r) == "vocabulary"
    r = _reasoning(error="pausas largas", categoria="fluidez")
    assert classify_error(r) == "fluency"


def test_classify_falls_back_to_keywords_in_description() -> None:
    r = _reasoning(error="Conjugación incorrecta: 'buyed' no existe.")
    assert classify_error(r) == "grammar"
    r = _reasoning(error="Usó una palabra equivocada para 'andén'.")
    assert classify_error(r) == "vocabulary"


def test_classify_defaults_to_grammar_for_unrecognized_text() -> None:
    r = _reasoning(error="xyz", categoria="unknown-category")
    assert classify_error(r) == "grammar"


# 3. StudentModelService.update_after_turn


@pytest.mark.asyncio
async def test_update_creates_default_model_on_first_turn() -> None:
    service, repo = _make_service(existing_model=None)

    model = await service.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, _reasoning(vocab=["Ticket", "platform"])
    )

    assert model is not None
    repo.save_model.assert_called_once()
    assert model["session_turns"] == 1
    assert model["bkt"]["attempts"] == 1
    assert model["bkt"]["p_learned"] > 0.2
    assert model["vocabulary"]["ticket"]["exposures"] == 1
    assert model["vocabulary"]["ticket"]["correct"] == 1
    assert model["vocabulary"]["ticket"]["errors"] == 0


@pytest.mark.asyncio
async def test_update_with_error_increments_patterns_and_vocab_errors() -> None:
    service, _ = _make_service(existing_model=None)

    model = await service.update_after_turn(
        TEST_USER_ID,
        TEST_LESSON_ID,
        _reasoning(error="Conjugación incorrecta", categoria="gramatica",
                   vocab=["ticket"]),
    )

    assert model is not None
    assert model["error_patterns"]["grammar"] == 1
    assert model["vocabulary"]["ticket"]["errors"] == 1
    assert model["vocabulary"]["ticket"]["correct"] == 0
    assert model["bkt"]["p_learned"] < 0.2 + 0.15


@pytest.mark.asyncio
async def test_update_accumulates_on_existing_model() -> None:
    existing = create_default_model()
    existing["vocabulary"]["ticket"] = {
        "exposures": 2, "correct": 2, "errors": 0, "last_seen": "2026-07-01T00:00:00Z"
    }
    existing["session_turns"] = 2
    existing["bkt"] = BktState(p_learned=0.5, attempts=2, last_updated=None)
    service, _ = _make_service(existing_model=existing)

    model = await service.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, _reasoning(vocab=["ticket"])
    )

    assert model is not None
    assert model["vocabulary"]["ticket"]["exposures"] == 3
    assert model["session_turns"] == 3
    assert model["bkt"]["attempts"] == 3


@pytest.mark.asyncio
async def test_update_skips_system_error_reasoning() -> None:
    """Invalid LLM output says nothing about the student -> no update."""
    service, repo = _make_service()

    result = await service.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, {"error": "invalid_json_from_llm"}
    )

    assert result is None
    repo.save_model.assert_not_called()


@pytest.mark.asyncio
async def test_update_never_raises_on_repository_failure() -> None:
    """The student model must never break /turn."""
    service, repo = _make_service()
    repo.save_model = AsyncMock(side_effect=RuntimeError("supabase down"))

    result = await service.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, _reasoning(vocab=["ticket"])
    )

    assert result is None


def test_student_context_summarizes_model() -> None:
    service, _ = _make_service()
    model = create_default_model()
    model["bkt"] = BktState(p_learned=0.72, attempts=8, last_updated=None)
    model["session_turns"] = 4
    model["error_patterns"] = ErrorPatterns(
        pronunciation=0, grammar=3, vocabulary=1, fluency=0
    )
    model["vocabulary"]["buyed"] = {
        "exposures": 3, "correct": 1, "errors": 2, "last_seen": "2026-07-01T00:00:00Z"
    }

    context = service.get_student_context(model)

    assert "practicing" in context
    assert "grammar x3" in context
    assert "'buyed'" in context


def test_student_context_handles_missing_model() -> None:
    service, _ = _make_service()
    assert "no data yet" in service.get_student_context(None)


# 4. Repository fallback tests

def _sample_model() -> StudentModel:
    model = create_default_model()
    model["session_turns"] = 5
    return model


@pytest.mark.asyncio
async def test_repository_returns_redis_copy_when_present() -> None:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=json.dumps(_sample_model()))
    supabase = MagicMock()
    repo = StudentModelRepository(redis, supabase)

    model = await repo.get_model(TEST_USER_ID, TEST_LESSON_ID)

    assert model is not None
    assert model["session_turns"] == 5
    supabase.table.assert_not_called()


@pytest.mark.asyncio
async def test_repository_falls_back_to_supabase_and_rehydrates() -> None:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)

    sample = _sample_model()
    result = MagicMock()
    result.data = [
        {
            "vocabulary": sample["vocabulary"],
            "error_patterns": sample["error_patterns"],
            "bkt": sample["bkt"],
            "session_turns": sample["session_turns"],
        }
    ]
    supabase = MagicMock()
    query = supabase.table.return_value.select.return_value
    query.eq.return_value.eq.return_value.execute.return_value = result
    repo = StudentModelRepository(redis, supabase)

    model = await repo.get_model(TEST_USER_ID, TEST_LESSON_ID)

    assert model is not None
    assert model["session_turns"] == 5
    redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_repository_returns_none_when_nowhere() -> None:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    result = MagicMock()
    result.data = []
    supabase = MagicMock()
    query = supabase.table.return_value.select.return_value
    query.eq.return_value.eq.return_value.execute.return_value = result
    repo = StudentModelRepository(redis, supabase)

    assert await repo.get_model(TEST_USER_ID, TEST_LESSON_ID) is None


@pytest.mark.asyncio
async def test_repository_save_writes_redis_and_supabase() -> None:
    redis = MagicMock()
    redis.set = AsyncMock(return_value=True)
    supabase = MagicMock()
    repo = StudentModelRepository(redis, supabase)

    await repo.save_model(TEST_USER_ID, TEST_LESSON_ID, _sample_model())

    redis.set.assert_called_once()
    supabase.table.assert_called_with("student_models")
    upsert_kwargs = supabase.table.return_value.upsert.call_args
    assert upsert_kwargs.kwargs["on_conflict"] == "user_id,lesson_id"


@pytest.mark.asyncio
async def test_repository_save_survives_redis_failure() -> None:
    """Redis down -> Supabase still receives the durable copy."""
    redis = MagicMock()
    redis.set = AsyncMock(side_effect=ConnectionError("redis down"))
    supabase = MagicMock()
    repo = StudentModelRepository(redis, supabase)

    await repo.save_model(TEST_USER_ID, TEST_LESSON_ID, _sample_model())

    supabase.table.assert_called_with("student_models")


# 5. Endpoint integration test 


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    return TestClient(app, raise_server_exceptions=False)


def test_get_student_model_endpoint(client: TestClient) -> None:
    model = create_default_model()
    model["bkt"] = BktState(
        p_learned=0.72, attempts=8, last_updated="2026-07-18T00:00:00Z"
    )
    model["session_turns"] = 4
    model["error_patterns"]["grammar"] = 2
    model["vocabulary"]["ticket"] = {
        "exposures": 5, "correct": 4, "errors": 1, "last_seen": "2026-07-18T00:00:00Z"
    }

    mock_service = MagicMock()
    mock_service.get_model = AsyncMock(return_value=model)
    app.dependency_overrides[get_student_model_service] = lambda: mock_service
    try:
        response = client.get(
            f"/v1/progress/lesson/{TEST_LESSON_ID}/student-model",
            headers=_auth_headers(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["lesson_id"] == TEST_LESSON_ID
    assert body["mastery_level"] == "practicing"
    assert body["p_learned"] == 0.72
    assert body["session_turns"] == 4
    assert body["error_patterns"]["grammar"] == 2
    assert body["vocabulary"] == [
        {
            "term": "ticket",
            "exposures": 5,
            "correct": 4,
            "errors": 1,
            "success_rate": 0.8,
        }
    ]


def test_get_student_model_requires_auth(client: TestClient) -> None:
    response = client.get(f"/v1/progress/lesson/{TEST_LESSON_ID}/student-model")
    assert response.status_code in (401, 403)
