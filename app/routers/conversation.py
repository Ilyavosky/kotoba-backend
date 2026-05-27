from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.auth import AuthUser
from app.core.deps import get_groq_client, get_redis_repository
from app.schemas.conversation import ConversationTurnResponse
from app.services.conversation_orchestration import ConversationOrchestrationService

router = APIRouter(prefix="/v1/conversation", tags=["conversation"])

@router.post("/turn", response_model=ConversationTurnResponse)
async def conversation_turn(
    current_user: AuthUser,
    audio_file: UploadFile = File(...),
    lesson_id: str = Form(...),
    groq_client = Depends(get_groq_client),
    repository = Depends(get_redis_repository)
    ) -> ConversationTurnResponse:
        audio_bytes = await audio_file.read()
        service = ConversationOrchestrationService(groq_client, repository)
        return await service.process_turn(audio_bytes, lesson_id, current_user.user_id)
