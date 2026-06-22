import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from groq import Groq

logger = logging.getLogger(__name__)

_FALLBACK_INTERVENCION = "¿Puedes contarme un poco más?"
_FALLBACK_RAZONAMIENTO: dict[str, Any] = {"error": "invalid_json_from_llm"}
_LLM_TIMEOUT = 15.0  # seconds


class AgentService:
    def __init__(self, groq_client: Groq, system_prompt: str, model: str) -> None:
        self._groq = groq_client
        self._system_prompt = system_prompt
        self._model = model

    async def generate_response(
        self,
        lesson: dict[str, Any],
        history: list[dict[str, Any]],
        transcription: str,
    ) -> tuple[str, dict[str, Any]]:
        user_message = json.dumps(
            {
                "leccion": lesson,
                "historial": history,
                "turno_estudiante": transcription,
            },
            ensure_ascii=False,
        )

        try:
            completion = await asyncio.wait_for(
                asyncio.to_thread(self._call_llm, user_message),
                timeout=_LLM_TIMEOUT,
            )
            raw = completion.choices[0].message.content or ""
            parsed: dict[str, Any] = json.loads(raw)
        except Exception as e:
            logger.error("agent_error: %s", e)
            return _FALLBACK_INTERVENCION, _FALLBACK_RAZONAMIENTO

        intervencion: str = parsed.get("intervencion", _FALLBACK_INTERVENCION)
        razonamiento: dict[str, Any] = parsed.get("razonamiento", {})

        logger.info("agent_ok paso=%s", razonamiento.get("paso_aplicado"))
        return intervencion, razonamiento

    def _call_llm(self, user_message: str) -> Any:
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
    """
    Reads the system prompt from disk once and returns a ready AgentService.
    Called at module load in deps.py — prompt is cached for the lifetime of the process.
    """
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "agent_v1.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")
    return AgentService(groq_client, system_prompt, model)
