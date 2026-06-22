import asyncio
import time
from typing import Any

import structlog
from fastapi import HTTPException
from groq import Groq

from app.repositories.conversation_context import ConversationContextRepository
from app.repositories.lesson_repository import LessonRepository
from app.schemas.conversation import ConversationTurnResponse
from app.services.agent_service import AgentService
from app.services.tts_service import TtsService

logger = structlog.get_logger(__name__)

_ASR_TIMEOUT = 20.0  # seconds


class ConversationOrchestrationService:
    def __init__(
        self,
        groq_client: Groq,
        repository: ConversationContextRepository,
        lesson_repository: LessonRepository,
        agent_service: AgentService,
        tts_service: TtsService,
    ) -> None:
        self.groq_client = groq_client
        self.repository = repository
        self.lesson_repository = lesson_repository
        self.agent_service = agent_service
        self.tts_service = tts_service

    async def process_turn(
        self, audio_bytes: bytes, lesson_id: str, user_id: str
    ) -> ConversationTurnResponse:
        structlog.contextvars.bind_contextvars(user_id=user_id, lesson_id=lesson_id)

        # 1. Load lesson and conversation history
        lesson, history = await self._load_context(user_id, lesson_id)

        # 2. Transcribe audio (ASR)
        transcription = await self._transcribe(audio_bytes)

        # 3. Generate agent response
        intervencion, razonamiento = await self.agent_service.generate_response(
            lesson=lesson,
            history=history,
            transcription=transcription,
        )
        logger.info("agent_done", paso=razonamiento.get("paso_aplicado"))

        # 4. Synthesize audio (TTS) -- never blocks the response
        audio_url = await self.tts_service.synthesize(intervencion)

        # 5. Persist turn to Redis
        await self._save_turn(user_id, lesson_id, transcription, intervencion)

        return ConversationTurnResponse(
            transcription=transcription,
            agent_response=intervencion,
            audio_url=audio_url,
        )

    async def _load_context(
        self, user_id: str, lesson_id: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        lesson = await self.lesson_repository.get_lesson(lesson_id)

        try:
            history = await self.repository.get_history(user_id, lesson_id)
        except Exception as e:
            history = []
            logger.warning(
                "redis_unavailable", error=str(e), fallback="empty_context"
            )

        return lesson, history

    async def _transcribe(self, audio_bytes: bytes) -> str:
        try:
            t0 = time.perf_counter()
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.groq_client.audio.transcriptions.create,
                    file=("audio.webm", audio_bytes),
                    model="whisper-large-v3",
                ),
                timeout=_ASR_TIMEOUT,
            )
            logger.info(
                "asr_completed",
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                chars=len(result.text),
            )
            return str(result.text)
        except Exception as e:
            raise HTTPException(
                status_code=502, detail="ASR service unavailable"
            ) from e

    async def _save_turn(
        self,
        user_id: str,
        lesson_id: str,
        transcription: str,
        intervencion: str,
    ) -> None:
        try:
            await self.repository.append_turn(
                user_id, lesson_id, transcription, intervencion
            )
        except Exception as e:
            logger.warning("redis_save_failed", error=str(e))
