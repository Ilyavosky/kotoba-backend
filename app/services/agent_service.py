import asyncio
import json
import logging
from pathlib import Path
from typing import cast

from groq import Groq
from groq.types.chat import ChatCompletion

from app.schemas.domain import AgentReasoning, ConversationTurn

logger = logging.getLogger(__name__)

_FALLBACK_INTERVENCION = "Puedes contarme un poco mas?"
_FALLBACK_RAZONAMIENTO: AgentReasoning = {"error": "invalid_json_from_llm"}
_LLM_TIMEOUT = 15.0  # seconds


class AgentService:
    def __init__(self, groq_client: Groq, system_prompt: str, model: str) -> None:
        self._groq = groq_client
        self._system_prompt = system_prompt
        self._model = model

    async def generate_response(
        self,
        lesson: dict[str, object],
        history: list[ConversationTurn],
        transcription: str,
        step_context: str,
        student_context: str = "",
    ) -> tuple[str, AgentReasoning]:
        user_message = json.dumps(
            {
                "leccion": lesson,
                "historial": history,
                "turno_estudiante": transcription,
                "contexto_paso": step_context,
                "contexto_estudiante": student_context,
            },
            ensure_ascii=False,
        )

        try:
            completion = await asyncio.wait_for(
                asyncio.to_thread(self._call_llm, user_message),
                timeout=_LLM_TIMEOUT,
            )
            raw = completion.choices[0].message.content or ""
            parsed = cast(dict[str, object], json.loads(raw))
        except Exception as e:
            logger.error("agent_error: %s", e)
            return _FALLBACK_INTERVENCION, _FALLBACK_RAZONAMIENTO

        intervencion = cast(str, parsed.get("intervencion", _FALLBACK_INTERVENCION))
        razonamiento = cast(AgentReasoning, parsed.get("razonamiento", {}))

        logger.info("agent_ok paso=%s", razonamiento.get("paso_aplicado"))
        return intervencion, razonamiento

    def _call_llm(self, user_message: str) -> ChatCompletion:
        return self._groq.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )


def load_agent_service(groq_client: Groq, model: str) -> AgentService:
    # Reads the system prompt from disk once and returns a ready AgentService.
    # Called at module load in deps.py -- prompt cached for the process lifetime.
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "agent_v1.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")
    return AgentService(groq_client, system_prompt, model)
