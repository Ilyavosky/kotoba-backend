from typing import Literal, TypedDict


class ConversationTurn(TypedDict):
    """A single turn in a conversation, as stored in Redis."""

    rol: Literal["estudiante", "agente"]
    contenido: str


class AgentReasoning(TypedDict, total=False):
    """Structured reasoning returned by the pedagogical agent.

    All fields are optional (total=False) because the LLM may omit fields
    it deems irrelevant, and the fallback only sets 'error'.

    Field names are Spanish to match the JSON keys the LLM returns.
    """

    paso_aplicado: str
    error_detectado: str | None
    vocabulario_activado: list[str]
    siguiente_objetivo: str
    error: str


class StepState(TypedDict):
    current_step: int
    turns_on_step: int
    consecutive_errors: int
    completed: bool
