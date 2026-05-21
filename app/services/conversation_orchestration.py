import time

import structlog

from app.schemas.conversation import ConversationTurnResponse

logger = structlog.get_logger(__name__)

class ConversationOrchestrationService:
    def __init__(self, groq_client):
        self.groq_client = groq_client
    async def process_turn(self, audio_bytes, lesson_id, user_id):
        structlog.contextvars.bind_contextvars(user_id=user_id, lesson_id=lesson_id)
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

        return ConversationTurnResponse(
            transcription= transcription.text,
            agent_response="stub: respuesta del agente",
            audio_url=None
            )

