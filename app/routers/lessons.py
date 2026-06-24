from fastapi import APIRouter, Depends

from app.core.auth import AuthUser
from app.core.deps import get_lesson_repository
from app.repositories.lesson_repository import LessonRepository

router = APIRouter(prefix="/v1/lessons", tags=["lesson"])

@router.get("/{lesson_id}")
async def get_lesson(
    lesson_id: str,
    current_user: AuthUser,
    lesson_repository: LessonRepository = Depends(get_lesson_repository),
) -> dict[str, object]:
    return await lesson_repository.get_lesson(lesson_id)
