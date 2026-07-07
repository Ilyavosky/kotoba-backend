"""
Unit tests: DecisionEngineService.update_after_turn — decision logging

These tests bypass HTTP entirely and exercise the service directly.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.domain import AgentReasoning, StepState
from app.services.decision_engine import DecisionEngineService

# ── Helpers ───────────────────────────────────────────────────────────────────

TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_LESSON_ID = "lesson-001"


def _make_engine(
    log_side_effect: Exception | None = None,
) -> tuple[DecisionEngineService, MagicMock, MagicMock, MagicMock]:
    """Return (engine, step_repo_mock, progress_repo_mock, log_repo_mock)."""
    step_repo = MagicMock()
    step_repo.save_step_state = AsyncMock(return_value=None)

    progress_repo = MagicMock()
    progress_repo.upsert_progress = AsyncMock(return_value=None)

    log_repo = MagicMock()
    if log_side_effect:
        log_repo.log_decision = AsyncMock(side_effect=log_side_effect)
    else:
        log_repo.log_decision = AsyncMock(return_value=None)

    engine = DecisionEngineService(step_repo, progress_repo, log_repo)
    return engine, step_repo, progress_repo, log_repo


def _state(step: int = 1, turns: int = 0, errors: int = 0) -> StepState:
    return StepState(
        current_step=step,
        turns_on_step=turns,
        consecutive_errors=errors,
        completed=False,
    )


def _reasoning(error: str | None = None) -> AgentReasoning:
    """A valid reasoning always carries paso_aplicado (see agent_v1.md)."""
    r: AgentReasoning = {"paso_aplicado": "4"}
    if error:
        r["error_detectado"] = error
    return r


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_called_with_stay_error_when_error_detected() -> None:
    """Error in reasoning → decision='stay_error', step unchanged."""
    engine, _, _, log_repo = _make_engine()
    state = _state(step=2, turns=1)

    await engine.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, state, _reasoning(error="wrong tense")
    )

    log_repo.log_decision.assert_called_once()
    call_kwargs = log_repo.log_decision.call_args.kwargs
    assert call_kwargs["decision"] == "stay_error"
    assert call_kwargs["step_before"] == 2
    assert call_kwargs["step_after"] == 2
    assert call_kwargs["error_detected"] == "wrong tense"


@pytest.mark.asyncio
async def test_log_called_with_stay_clean_when_turns_insufficient() -> None:
    """No error but only 1 turn on step (< 2) → 'stay_clean', step unchanged."""
    engine, _, _, log_repo = _make_engine()
    state = _state(step=3, turns=0)

    await engine.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, state, _reasoning()
    )

    log_repo.log_decision.assert_called_once()
    call_kwargs = log_repo.log_decision.call_args.kwargs
    assert call_kwargs["decision"] == "stay_clean"
    assert call_kwargs["step_before"] == 3
    assert call_kwargs["step_after"] == 3
    assert call_kwargs["error_detected"] is None


@pytest.mark.asyncio
async def test_log_called_with_advance_when_step_progresses() -> None:
    """No error and turns reach threshold → 'advance', step_after = before + 1."""
    engine, _, _, log_repo = _make_engine()
    state = _state(step=2, turns=1)  # turns_on_step will hit 2 → advance

    await engine.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, state, _reasoning()
    )

    log_repo.log_decision.assert_called_once()
    call_kwargs = log_repo.log_decision.call_args.kwargs
    assert call_kwargs["decision"] == "advance"
    assert call_kwargs["step_before"] == 2
    assert call_kwargs["step_after"] == 3


@pytest.mark.asyncio
async def test_llm_failure_is_noop_but_logged() -> None:
    """LLM technical error: state untouched, but logged as system_error."""
    engine, step_repo, progress_repo, log_repo = _make_engine()
    state = _state(step=2, turns=1)

    result = await engine.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, state, {"error": "invalid_json_from_llm"}
    )

    assert result["current_step"] == 2
    assert result["turns_on_step"] == 1
    step_repo.save_step_state.assert_not_called()
    progress_repo.upsert_progress.assert_not_called()
    log_repo.log_decision.assert_called_once()
    call_kwargs = log_repo.log_decision.call_args.kwargs
    assert call_kwargs["decision"] == "system_error"
    assert call_kwargs["step_before"] == 2
    assert call_kwargs["step_after"] == 2


@pytest.mark.asyncio
async def test_empty_reasoning_is_system_error() -> None:
    """Silent route: valid JSON without razonamiento → {} must NOT advance."""
    engine, step_repo, progress_repo, log_repo = _make_engine()
    state = _state(step=3, turns=1, errors=2)

    result = await engine.update_after_turn(TEST_USER_ID, TEST_LESSON_ID, state, {})

    assert result["current_step"] == 3
    assert result["turns_on_step"] == 1
    assert result["consecutive_errors"] == 2  # error streak NOT reset
    step_repo.save_step_state.assert_not_called()
    progress_repo.upsert_progress.assert_not_called()
    assert log_repo.log_decision.call_args.kwargs["decision"] == "system_error"


@pytest.mark.asyncio
async def test_prompt_fallback_is_system_error() -> None:
    """The prompt's own fallback ('contexto insuficiente') must also be a no-op."""
    engine, step_repo, progress_repo, _ = _make_engine()
    state = _state(step=2, turns=1)

    result = await engine.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, state, {"error": "contexto insuficiente"}
    )

    assert result["current_step"] == 2
    assert result["turns_on_step"] == 1
    step_repo.save_step_state.assert_not_called()
    progress_repo.upsert_progress.assert_not_called()


@pytest.mark.asyncio
async def test_llm_failure_on_final_step_does_not_complete() -> None:
    """Max-damage scenario: step 6, turns=1, LLM timeout → must NOT graduate."""
    engine, step_repo, progress_repo, _ = _make_engine()
    state = _state(step=6, turns=1)

    result = await engine.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, state, {"error": "invalid_json_from_llm"}
    )

    assert result["completed"] is False
    assert result["current_step"] == 6
    progress_repo.upsert_progress.assert_not_called()


@pytest.mark.asyncio
async def test_completed_lesson_is_guarded() -> None:
    """A turn on an already-completed lesson: no mutation, no spurious log."""
    engine, step_repo, progress_repo, log_repo = _make_engine()
    state = StepState(
        current_step=6, turns_on_step=2, consecutive_errors=0, completed=True
    )

    result = await engine.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, state, _reasoning()
    )

    assert result["completed"] is True
    assert result["current_step"] == 6
    step_repo.save_step_state.assert_not_called()
    progress_repo.upsert_progress.assert_not_called()
    log_repo.log_decision.assert_not_called()


@pytest.mark.asyncio
async def test_log_failure_does_not_raise() -> None:
    """log_decision raising must NOT propagate — fire-and-forget guaranteed."""
    engine, _, _, log_repo = _make_engine(log_side_effect=Exception("Supabase down"))
    state = _state(step=1, turns=0)

    # Should not raise even though log_repo.log_decision raises
    result = await engine.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, state, _reasoning(error="bad pronunciation")
    )

    assert result["current_step"] == 1  # state still returned correctly
