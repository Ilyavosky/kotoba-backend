import time

import structlog

from app.schemas.conversation import ConversationTurnResponse

from fastapi import HTTPException

logger = structlog.get_logger(__name__)

class ConversationOrchestrationService:
    def __init__(self, groq_client, repository):
        self.groq_client = groq_client
        self.repository = repository
    async def process_turn(self, audio_bytes, lesson_id, user_id):
        structlog.contextvars.bind_contextvars(user_id=user_id, lesson_id=lesson_id)

        try:    
            history = await self.repository.get_history(user_id, lesson_id)
        except Exception as er:
            history = []
            logger.warning("redis_unavailable", error=str(er), fallback="empty_context")
            
        
        try:
            t0 = time.perf_counter()
            transcription = self.groq_client.audio.transcriptions.create(
            #Might need to change depending of the type of file
            file = ("audio.webm", audio_bytes),
            model = "whisper-large-v3",
            )
            asr_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.info("asr_completed",
                    latency_ms=asr_ms,
                    transcription_chars=len(transcription.text)
                    )
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail="ASR service unavailable"
                )from e
        
        await self.repository.append_turn(user_id, lesson_id, transcription.text, "stub: respuesta del agente")
        
        return ConversationTurnResponse(
            transcription= transcription.text,
            agent_response="stub: respuesta del agente",
            audio_url=None
        )