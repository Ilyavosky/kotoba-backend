from typing import Literal
from pydantic import BaseModel

class LessonProgressResponse (BaseModel):
    lesson_id: str
    current_step: int
    status: Literal["not_started", "in_progress", "completed"]
    turns_on_step: int
    consecutive_errors: int

class ModuleLessonProgress(BaseModel):
    lesson_id: str
    current_step: int
    status: Literal["not_started", "in_progress", "completed"]
    
class ModuleProgressResponse(BaseModel):
    lessons: list[ModuleLessonProgress]