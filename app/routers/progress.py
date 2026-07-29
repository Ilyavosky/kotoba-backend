from typing import Literal, cast

from fastapi import APIRouter, Depends

from app.core.auth import AuthUser
from app.core.deps import (
    get_decision_engine_service,
    get_module_repository,
    get_student_model_service,
    get_student_progress_repository,
)
from app.repositories.module_repository import ModuleRepository
from app.repositories.student_progress_repository import StudentProgressRepository
from app.schemas.progress import (
    LessonProgressResponse,
    ModuleLessonProgress,
    ModuleProgressResponse,
)
from app.schemas.student_model import StudentModelResponse, VocabularyItemSummary
from app.services.decision_engine import DecisionEngineService
from app.services.student_model_service import StudentModelService, get_mastery_level

router = APIRouter(prefix="/v1/progress", tags=["progress"])

@router.get("/lesson/{lesson_id}", response_model=LessonProgressResponse)
async def get_lesson_progress(
    lesson_id: str,
    user: AuthUser,
    decision_engine: DecisionEngineService = Depends(get_decision_engine_service),
    progress_repo: StudentProgressRepository = Depends(get_student_progress_repository),
) -> LessonProgressResponse:
    state = await decision_engine.get_current_state(user.user_id, lesson_id)
    progress = await progress_repo.get_progress(user.user_id, lesson_id)

    # Supabase is the durable source of truth for status -- same source that
    # /module/{id} uses, so both endpoints can never contradict each other.
    # Redis state only refines the numeric detail within its TTL window.
    status: Literal["not_started", "in_progress", "completed"]
    if state["completed"]:
        status = "completed"
    elif progress is not None:
        status = cast(
            Literal["not_started", "in_progress", "completed"], progress["status"]
        )
    elif state["current_step"] > 1 or state["turns_on_step"] > 0:
        # Live Redis activity not yet persisted to Supabase
        status = "in_progress"
    else:
        status = "not_started"

    return LessonProgressResponse(
        lesson_id=lesson_id,
        current_step=state["current_step"],
        status=status,
        turns_on_step=state["turns_on_step"],
        consecutive_errors=state["consecutive_errors"],
    )


@router.get(
    "/lesson/{lesson_id}/student-model", response_model=StudentModelResponse
)
async def get_student_model(
    lesson_id: str,
    user: AuthUser,
    student_model_service: StudentModelService = Depends(get_student_model_service),
) -> StudentModelResponse:
    """K-06.1: expose the student model (vocabulary, errors, BKT mastery)."""
    model = await student_model_service.get_model(user.user_id, lesson_id)

    vocabulary = [
        VocabularyItemSummary(
            term=term,
            exposures=entry["exposures"],
            correct=entry["correct"],
            errors=entry["errors"],
            success_rate=(
                round(entry["correct"] / entry["exposures"], 4)
                if entry["exposures"] > 0
                else 0.0
            ),
        )
        for term, entry in sorted(model["vocabulary"].items())
    ]

    return StudentModelResponse(
        lesson_id=lesson_id,
        mastery_level=get_mastery_level(model["bkt"]["p_learned"]),
        p_learned=round(model["bkt"]["p_learned"], 4),
        attempts=model["bkt"]["attempts"],
        session_turns=model["session_turns"],
        error_patterns=cast(dict[str, int], dict(model["error_patterns"])),
        vocabulary=vocabulary,
    )


@router.get("/module/{module_id}", response_model=ModuleProgressResponse)
async def get_module_progress(
    module_id: str,
    user: AuthUser,
    module_repo: ModuleRepository = Depends(get_module_repository),
    progress_repo: StudentProgressRepository = Depends(get_student_progress_repository),
) -> ModuleProgressResponse:
    lesson_ids = await module_repo.get_lesson_ids(module_id)

    lessons = []
    for lesson_id in lesson_ids:
        progress = await progress_repo.get_progress(user.user_id, lesson_id)
        if progress is None:
            lessons.append(ModuleLessonProgress(
                lesson_id=lesson_id,
                current_step=1,
                status="not_started",
            ))
        else:
            lessons.append(ModuleLessonProgress(
                lesson_id=lesson_id,
                current_step=int(progress["current_step"]),
                status=progress["status"],
            ))

    return ModuleProgressResponse(lessons=lessons)
