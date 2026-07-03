from fastapi import APIRouter, Depends

from app.core.auth import AuthUser
from app.core.deps import (
    get_decision_engine_service,
    get_module_repository,
    get_student_progress_repository,
)
from app.repositories.module_repository import ModuleRepository
from app.repositories.student_progress_repository import StudentProgressRepository
from app.schemas.progress import (
    LessonProgressResponse,
    ModuleLessonProgress,
    ModuleProgressResponse,
)
from app.services.decision_engine import DecisionEngineService

router = APIRouter(prefix="/v1/progress", tags=["progress"])


@router.get("/lesson/{lesson_id}", response_model=LessonProgressResponse)
async def get_lesson_progress(
    lesson_id: str,
    user: AuthUser,
    decision_engine: DecisionEngineService = Depends(get_decision_engine_service),
) -> LessonProgressResponse:
    state = await decision_engine.get_current_state(user.user_id, lesson_id)
    if state["completed"]:
        status = "completed"
    elif state["current_step"] == 1 and state["turns_on_step"] == 0:
        status = "not_started"
    else:
        status = "in_progress"
    return LessonProgressResponse(
        lesson_id=lesson_id,
        current_step=state["current_step"],
        status=status,
        turns_on_step=state["turns_on_step"],
        consecutive_errors=state["consecutive_errors"],
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
            lessons.append(
                ModuleLessonProgress(
                    lesson_id=lesson_id,
                    current_step=1,
                    status="not_started",
                )
            )
        else:
            lessons.append(
                ModuleLessonProgress(
                    lesson_id=lesson_id,
                    current_step=int(progress["current_step"]),
                    status=progress["status"],  # type: ignore[arg-type]
                )
            )
    return ModuleProgressResponse(lessons=lessons)
