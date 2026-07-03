from groq import Groq
from supabase import Client, create_client

from app.core.config import settings
from app.core.redis import redis_client
from app.repositories.conversation_context import ConversationContextRepository
from app.repositories.lesson_repository import LessonRepository
from app.repositories.module_repository import ModuleRepository
from app.repositories.step_state_repository import StepStateRepository
from app.repositories.student_progress_repository import StudentProgressRepository
from app.repositories.decision_log_repository import DecisionLogRepository
from app.services.agent_service import AgentService, load_agent_service
from app.services.decision_engine import DecisionEngineService
from app.services.tts_service import TtsService

# Supabase client is created once at module load -- it's thread-safe and reusable
_supabase_client: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE,
)

# Shared Groq client -- reused by agent and TTS to avoid multiple instances
_groq_client = Groq(api_key=settings.GROQ_API_KEY)

# LessonRepository is also a singleton -- its in-memory cache lives here
_lesson_repository = LessonRepository(_supabase_client, settings.LESSONS_BUCKET)

# AgentService reads the prompt from disk once at startup
_agent_service: AgentService = load_agent_service(
    groq_client=_groq_client, model=settings.LLM_MODEL
)

# TtsService is stateless -- one instance shared across all requests
_tts_service = TtsService(_groq_client, _supabase_client, settings.TTS_BUCKET)

_step_state_repository = StepStateRepository(redis_client)

_student_progress_repository = StudentProgressRepository(_supabase_client)

_module_repository = ModuleRepository(_supabase_client)

_decision_log_repository = DecisionLogRepository(_supabase_client)

_decision_engine_service = DecisionEngineService(
    _step_state_repository,
    _student_progress_repository,
    _decision_log_repository,
)


def get_groq_client() -> Groq:
    return _groq_client


def get_supabase_client() -> Client:
    return _supabase_client


def get_lesson_repository() -> LessonRepository:
    return _lesson_repository


def get_agent_service() -> AgentService:
    return _agent_service


def get_tts_service() -> TtsService:
    return _tts_service


def get_redis_repository() -> ConversationContextRepository:
    return ConversationContextRepository(redis_client)


def get_module_repository() -> ModuleRepository:
    return _module_repository


def get_decision_engine_service() -> DecisionEngineService:
    return _decision_engine_service

def get_student_progress_repository() -> StudentProgressRepository:
    return _student_progress_repository
def get_decision_log_repository() -> DecisionLogRepository:
    return _decision_log_repository
