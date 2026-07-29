from typing import Literal, TypedDict

from pydantic import BaseModel

ErrorCategory = Literal["pronunciation", "grammar", "vocabulary", "fluency"]

MasteryLevel = Literal["introducing", "practicing", "mastered"]


class VocabularyEntry(TypedDict):
    """Exposure metadata for a single vocabulary item.

    exposures = correct + errors. The success ratio (correct / exposures)
    is the simplified spaced-repetition signal proposed in the K-06 research
    (Settles & Meeder, 2016 -- full forgetting curves are out of MVP scope).
    """

    exposures: int
    correct: int
    errors: int
    last_seen: str


class ErrorPatterns(TypedDict):
    """Per-session counters of error categories (see research section 2.3)."""

    pronunciation: int
    grammar: int
    vocabulary: int
    fluency: int


class BktState(TypedDict):
    """Bayesian Knowledge Tracing state for the active lesson.

    p_learned is P(L): the probability the student has learned the skill.
    Mastery criterion: P(L) >= 0.95 (Corbett & Anderson, 1995).
    """

    p_learned: float
    attempts: int
    last_updated: str | None


class StudentModel(TypedDict):
    """Full student model for one (user, lesson) pair.

    Stored in Redis under 'student:{user_id}:{lesson_id}' (active session,
    24h TTL) and mirrored to Supabase 'student_models' (durable state).
    Curricular position (current step) is NOT duplicated here -- it lives
    in StepState (step_state_repository), the single source of truth.
    """

    vocabulary: dict[str, VocabularyEntry]
    error_patterns: ErrorPatterns
    bkt: BktState
    session_turns: int


class VocabularyItemSummary(BaseModel):
    term: str
    exposures: int
    correct: int
    errors: int
    success_rate: float


class StudentModelResponse(BaseModel):
    lesson_id: str
    mastery_level: MasteryLevel
    p_learned: float
    attempts: int
    session_turns: int
    error_patterns: dict[str, int]
    vocabulary: list[VocabularyItemSummary]
