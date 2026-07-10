from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from groq import Groq

from app.core.auth import AuthUser
from app.core.capacity import CapacityLimiter
from app.core.config import settings
from app.core.deps import (
    get_agent_service,
    get_decision_engine_service,
    get_groq_client,
    get_lesson_repository,
    get_module_repository,
    get_rate_limiter,
    get_redis_repository,
    get_tts_service,
    get_turn_capacity_limiter,
)
from app.core.rate_limit import RateLimiter
from app.repositories.conversation_context import ConversationContextRepository
from app.repositories.lesson_repository import LessonRepository
from app.repositories.module_repository import ModuleRepository
from app.schemas.conversation import ConversationTurnResponse
from app.services.agent_service import AgentService
from app.services.conversation_orchestration import ConversationOrchestrationService
from app.services.decision_engine import DecisionEngineService
from app.services.tts_service import TtsService

router = APIRouter(prefix="/v1/conversation", tags=["conversation"])


@router.post("/turn", response_model=ConversationTurnResponse)
async def conversation_turn(
    current_user: AuthUser,
    audio_file: UploadFile = File(...),
    lesson_id: str = Form(...),
    groq_client: Groq = Depends(get_groq_client),
    repository: ConversationContextRepository = Depends(get_redis_repository),
    lesson_repository: LessonRepository = Depends(get_lesson_repository),
    agent_service: AgentService = Depends(get_agent_service),
    tts_service: TtsService = Depends(get_tts_service),
    decision_engine: DecisionEngineService = Depends(get_decision_engine_service),
    module_repository: ModuleRepository = Depends(get_module_repository),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    capacity: CapacityLimiter = Depends(get_turn_capacity_limiter),
) -> ConversationTurnResponse:
    # K-07.2 -- stability under load: rate limit per user (429), cap upload
    # size (413) and bound concurrent turns (503 when saturated).
    await rate_limiter.check(current_user.user_id)

    audio_bytes = await audio_file.read()
    if len(audio_bytes) > settings.MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file too large",
        )

    service = ConversationOrchestrationService(
        groq_client=groq_client,
        repository=repository,
        lesson_repository=lesson_repository,
        agent_service=agent_service,
        tts_service=tts_service,
        decision_engine=decision_engine,
        module_repository=module_repository,
    )
    async with capacity:
        return await service.process_turn(
            audio_bytes, lesson_id, current_user.user_id
        )
