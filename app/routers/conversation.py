from fastapi import APIRouter, Depends, File, Form, UploadFile
from groq import Groq

from app.core.auth import AuthUser
from app.core.deps import (
    get_agent_service,
    get_decision_engine_service,
    get_groq_client,
    get_lesson_repository,
    get_module_repository,
    get_redis_repository,
    get_tts_service,
)
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
) -> ConversationTurnResponse:
    audio_bytes = await audio_file.read()
    service = ConversationOrchestrationService(
        groq_client=groq_client,
        repository=repository,
        lesson_repository=lesson_repository,
        agent_service=agent_service,
        tts_service=tts_service,
        decision_engine=decision_engine,
        module_repository=module_repository,
    )
    return await service.process_turn(audio_bytes, lesson_id, current_user.user_id)
