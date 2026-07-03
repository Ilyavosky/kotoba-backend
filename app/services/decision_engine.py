import structlog
from app.repositories.decision_log_repository import DecisionLogRepository
from app.repositories.step_state_repository import StepStateRepository
from app.repositories.student_progress_repository import StudentProgressRepository
from app.schemas.domain import AgentReasoning, StepState

_TURNS_TO_ADVANCE = 2
_TOTAL_STEPS = 6


class DecisionEngineService:
    def __init__(
        self,
        repository: StepStateRepository,
        progress_repository: StudentProgressRepository,
        log_repository: DecisionLogRepository,
    ) -> None:
        self._repository = repository
        self._progress_repository = progress_repository
        self._log_repository = log_repository

    async def get_current_state(
        self,
        user_id: str,
        lesson_id: str,
    ) -> StepState:
        state = await self._repository.get_step_state(user_id, lesson_id)

        if state is None:
            progress = await self._progress_repository.get_progress(user_id, lesson_id)
            if progress is not None:
                return StepState(
                    current_step=int(progress["current_step"]),
                    turns_on_step=0,
                    consecutive_errors=0,
                    completed=False,
                )
            return StepState(
                current_step=1,
                turns_on_step=0,
                consecutive_errors=0,
                completed=False,
            )
        return state

    async def update_after_turn(
        self,
        user_id: str,
        lesson_id: str,
        state: StepState,
        reasoning: AgentReasoning,
    ) -> StepState:
        step_before = state["current_step"]
        has_error = bool(reasoning.get("error_detectado"))

        if has_error:
            state["consecutive_errors"] += 1
            state["turns_on_step"] += 1
            decision = "stay_error"
        else:
            state["consecutive_errors"] = 0
            state["turns_on_step"] += 1
            if state["turns_on_step"] >= _TURNS_TO_ADVANCE:
                if state["current_step"] < _TOTAL_STEPS:
                    state["current_step"] += 1
                    state["turns_on_step"] = 0
                else:
                    state["completed"] = True
                decision = "advance"
            else:
                decision = "stay_clean"

        await self._repository.save_step_state(user_id, lesson_id, state)
        status = "completed" if state["completed"] else "in_progress"
        await self._progress_repository.upsert_progress(
            user_id=user_id,
            lesson_id=lesson_id,
            current_step=state["current_step"],
            status=status,
        )
        try:
            await self._log_repository.log_decision(
                user_id=user_id,
                lesson_id=lesson_id,
                step_before=step_before,
                step_after=state["current_step"],
                decision=decision,
                error_detected=reasoning.get("error_detectado"),
                full_reasoning=dict(reasoning),
            )
        except Exception:
            structlog.get_logger().warning(
                "decision_log_unexpected_failure",
                user_id=user_id,
                lesson_id=lesson_id,
            )
        return state

    def get_step_context(
        self,
        state: StepState
    ) -> str:
        if state["completed"]:
            return "Lesson Completed"
        return (
            f"Current step: {state['current_step']}/{_TOTAL_STEPS}. "
            f"Turns on step: {state['turns_on_step']}. "
            f"Consecutive errors: {state['consecutive_errors']}."
        )
