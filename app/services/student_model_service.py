from datetime import UTC, datetime
from typing import cast

import structlog

from app.repositories.student_model_repository import StudentModelRepository
from app.schemas.domain import AgentReasoning
from app.schemas.student_model import (
    BktState,
    ErrorCategory,
    ErrorPatterns,
    MasteryLevel,
    StudentModel,
    VocabularyEntry,
)

logger = structlog.get_logger(__name__)

# Based on BKT parameters (Corbett & Anderson, 1995)
_P_L0 = 0.2  # P(L0): prior probability the skill is already known
_P_T = 0.15  # P(T):  probability of learning at each practice opportunity
_P_S = 0.1  # P(S):  slip as error despite knowing the skill
_P_G = 0.15  # P(G):  guess as success despite not knowing the skill

_MASTERY_THRESHOLD = 0.95
_PRACTICING_THRESHOLD = 0.5

_CATEGORY_MAP: dict[str, ErrorCategory] = {
    "pronunciacion": "pronunciation",
    "pronunciación": "pronunciation",
    "pronunciation": "pronunciation",
    "gramatica": "grammar",
    "gramática": "grammar",
    "grammar": "grammar",
    "vocabulario": "vocabulary",
    "vocabulary": "vocabulary",
    "lexico": "vocabulary",
    "léxico": "vocabulary",
    "fluidez": "fluency",
    "fluency": "fluency",
}


_KEYWORD_RULES: list[tuple[ErrorCategory, tuple[str, ...]]] = [
    ("pronunciation", ("pronunc", "fonema", "phoneme", "sonido")),
    ("vocabulary", ("palabra", "vocabulario", "léxic", "lexic", "word", "término")),
    ("fluency", ("pausa", "fluidez", "fluency", "reformul", "duda")),
    ("grammar", ("conjuga", "gramat", "grammar", "concordancia", "tiempo", "tense")),
]


def bkt_update(p_learned: float, correct: bool) -> float:
    """One BKT step: posterior given the observation, then learning transition.

    Pure function so Fernando can validate the math against the research doc
    and unit tests can cover it exhaustively.
    """
    if correct:
        numerator = p_learned * (1 - _P_S)
        denominator = numerator + (1 - p_learned) * _P_G
    else:
        numerator = p_learned * _P_S
        denominator = numerator + (1 - p_learned) * (1 - _P_G)

    posterior = numerator / denominator if denominator > 0 else p_learned
    updated = posterior + (1 - posterior) * _P_T
    return min(max(updated, 0.0), 1.0)


def get_mastery_level(p_learned: float) -> MasteryLevel:
    if p_learned >= _MASTERY_THRESHOLD:
        return "mastered"
    if p_learned >= _PRACTICING_THRESHOLD:
        return "practicing"
    return "introducing"


def classify_error(reasoning: AgentReasoning) -> ErrorCategory | None:
    """Map the agent's detected error to an auditable category.

    Preference order: explicit 'categoria_error' from the LLM, then keyword
    match over the free-text description, then 'grammar' as the most common
    category in conversational L2 errors.
    """
    if not reasoning.get("error_detectado"):
        return None

    categoria = (reasoning.get("categoria_error") or "").strip().lower()
    if categoria in _CATEGORY_MAP:
        return _CATEGORY_MAP[categoria]

    description = (reasoning.get("error_detectado") or "").lower()
    for category, keywords in _KEYWORD_RULES:
        if any(keyword in description for keyword in keywords):
            return category
    return "grammar"


def create_default_model() -> StudentModel:
    return StudentModel(
        vocabulary={},
        error_patterns=ErrorPatterns(
            pronunciation=0, grammar=0, vocabulary=0, fluency=0
        ),
        bkt=BktState(p_learned=_P_L0, attempts=0, last_updated=None),
        session_turns=0,
    )


class StudentModelService:
    def __init__(self, repository: StudentModelRepository) -> None:
        self._repository = repository

    async def get_model(self, user_id: str, lesson_id: str) -> StudentModel:
        model = await self._repository.get_model(user_id, lesson_id)
        return model if model is not None else create_default_model()

    async def update_after_turn(
        self,
        user_id: str,
        lesson_id: str,
        reasoning: AgentReasoning,
    ) -> StudentModel | None:
        """Update vocabulary, error patterns and BKT from one turn's reasoning.

        Never raises: the student model must not break /turn. On any failure
        it logs and returns None, leaving the previous state untouched.
        """
        if bool(reasoning.get("error")) or "paso_aplicado" not in reasoning:
            logger.info(
                "student_model_skip_system_error",
                user_id=user_id,
                lesson_id=lesson_id,
            )
            return None

        try:
            model = await self.get_model(user_id, lesson_id)
            now = datetime.now(UTC).isoformat()
            correct = not bool(reasoning.get("error_detectado"))

            # 1. Vocabulary exposures
            for term in reasoning.get("vocabulario_activado") or []:
                normalized = term.strip().lower()
                if not normalized:
                    continue
                entry = model["vocabulary"].get(
                    normalized,
                    VocabularyEntry(exposures=0, correct=0, errors=0, last_seen=now),
                )
                entry["exposures"] += 1
                if correct:
                    entry["correct"] += 1
                else:
                    entry["errors"] += 1
                entry["last_seen"] = now
                model["vocabulary"][normalized] = entry

            # 2. Error patterns
            category = classify_error(reasoning)
            if category is not None:
                model["error_patterns"][category] += 1

            # 3. BKT mastery
            model["bkt"]["p_learned"] = bkt_update(
                model["bkt"]["p_learned"], correct
            )
            model["bkt"]["attempts"] += 1
            model["bkt"]["last_updated"] = now

            model["session_turns"] += 1

            await self._repository.save_model(user_id, lesson_id, model)
            logger.info(
                "student_model_updated",
                p_learned=round(model["bkt"]["p_learned"], 4),
                mastery=get_mastery_level(model["bkt"]["p_learned"]),
                correct=correct,
                error_category=category,
            )
            return model
        except Exception as e:
            logger.warning(
                "student_model_update_failed",
                user_id=user_id,
                lesson_id=lesson_id,
                error=str(e),
            )
            return None

    def get_student_context(self, model: StudentModel | None) -> str:
        """Compact summary injected into the agent prompt each turn."""
        if model is None or model["bkt"]["attempts"] == 0:
            return "Student model: no data yet (first turn for this lesson)."

        bkt = model["bkt"]
        parts = [
            (
                f"Student model: mastery={get_mastery_level(bkt['p_learned'])} "
                f"(P(L)={bkt['p_learned']:.2f}, attempts={bkt['attempts']}, "
                f"session_turns={model['session_turns']})."
            )
        ]

        frequent = [
            f"{category} x{count}"
            for category, count in cast(
                dict[str, int], model["error_patterns"]
            ).items()
            if count > 0
        ]
        if frequent:
            parts.append("Frequent errors: " + ", ".join(frequent) + ".")

        weak = [
            f"'{term}' ({entry['correct']}/{entry['exposures']} ok)"
            for term, entry in model["vocabulary"].items()
            if entry["errors"] > entry["correct"]
        ]
        if weak:
            parts.append("Struggling vocabulary: " + ", ".join(sorted(weak)) + ".")

        return " ".join(parts)
