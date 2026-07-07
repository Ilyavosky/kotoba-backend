import asyncio
import time

import structlog
from fastapi import HTTPException
from groq import Groq

from app.repositories.conversation_context import ConversationContextRepository
from app.repositories.lesson_repository import LessonRepository
from app.repositories.module_repository import ModuleRepository
from app.schemas.conversation import ConversationTurnResponse
from app.schemas.domain import ConversationTurn
from app.services.agent_service import AgentService
from app.services.decision_engine import DecisionEngineService
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
        decision_engine: DecisionEngineService,
        module_repository: ModuleRepository,
    ) -> None:
        self.groq_client = groq_client
        self.repository = repository
        self.lesson_repository = lesson_repository
        self.agent_service = agent_service
        self.tts_service = tts_service
        self.decision_engine = decision_engine
        self.module_repository = module_repository

    async def process_turn(
        self, audio_bytes: bytes, lesson_id: str, user_id: str
    ) -> ConversationTurnResponse:
        structlog.contextvars.bind_contextvars(user_id=user_id, lesson_id=lesson_id)

        # 1. Load lesson and conversation history
        lesson, history = await self._load_context(user_id, lesson_id)

        state = await self.decision_engine.get_current_state(user_id, lesson_id)
        step_context = self.decision_engine.get_step_context(state)

        # 2. Transcribe audio (ASR)
        transcription = await self._transcribe(audio_bytes)

        # 3. Generate agent response
        intervencion, razonamiento = await self.agent_service.generate_response(
            lesson=lesson,
            history=history,
            transcription=transcription,
            step_context=step_context,
        )
        logger.info("agent_done", paso=razonamiento.get("paso_aplicado"))

        # 4. Kick off TTS concurrently -- it only needs `intervencion`, so it
        # overlaps with the state update and Redis persistence below.
        # It degrades gracefully: synthesize() catches everything and returns
        # None on failure, so awaiting it can never break the response.
        tts_task = asyncio.create_task(self.tts_service.synthesize(intervencion))

        # 5. Update step state
        updated_state = await self.decision_engine.update_after_turn(
            user_id, lesson_id, state, razonamiento
        )

        # 6. Resolve next lesson if current lesson just completed
        next_lesson_id: str | None = None
        if updated_state["completed"]:
            next_lesson_id = await self.module_repository.get_next_lesson_id(lesson_id)

        # 7. Persist turn to Redis
        await self._save_turn(user_id, lesson_id, transcription, intervencion)

        # 8. Collect the TTS result (already running since step 4)
        audio_url = await tts_task

        return ConversationTurnResponse(
            transcription=transcription,
            agent_response=intervencion,
            audio_url=audio_url,
            lesson_completed=updated_state["completed"],
            next_lesson_id=next_lesson_id,
        )

    async def _load_context(
        self, user_id: str, lesson_id: str
    ) -> tuple[dict[str, object], list[ConversationTurn]]:
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
