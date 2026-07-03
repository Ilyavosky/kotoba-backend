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
    r: AgentReasoning = {}
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
    """No error but only 1 turn on step (< 2) → decision='stay_clean', step unchanged."""
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
    """No error and turns reach threshold → decision='advance', step_after = step_before + 1."""
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
async def test_log_failure_does_not_raise() -> None:
    """log_decision raising must NOT propagate — fire-and-forget is guaranteed by the repo."""
    engine, _, _, log_repo = _make_engine(log_side_effect=Exception("Supabase down"))
    state = _state(step=1, turns=0)

    # Should not raise even though log_repo.log_decision raises
    result = await engine.update_after_turn(
        TEST_USER_ID, TEST_LESSON_ID, state, _reasoning(error="bad pronunciation")
    )

    assert result["current_step"] == 1  # state still returned correctly
