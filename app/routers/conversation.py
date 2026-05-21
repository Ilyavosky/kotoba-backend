from fastapi import APIRouter, File, Form, UploadFile

from app.core.auth import AuthUser
from app.schemas.conversation import ConversationTurnResponse

router = APIRouter(prefix="/v1/conversation", tags=["conversation"])

@router.post("/turn", response_model=ConversationTurnResponse)
async def conversation_turn(
    current_user: AuthUser,
    audio_file: UploadFile = File(...),
    lesson_id: str = Form(...)
    ) -> ConversationTurnResponse:
    return ConversationTurnResponse(
    transcription="stub: audio recibido",
    agent_response="stub: respuesta del agente",
    audio_url=None,
)
