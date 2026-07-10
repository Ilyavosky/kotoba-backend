from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Pydantic Class that validates the urls from the .env file
# Each secret must have at least 1 character lenght,
# If not, it automaticly throws ValidationError
class Settings(BaseSettings):
    SUPABASE_URL: str = Field(min_length=1, description="URL from the Supabase project")
    SUPABASE_ANON_KEY: str = Field(
        min_length=1, description="Anon Key from the Supabase project"
    )
    SUPABASE_JWT_SECRET: str = Field(
        min_length=1, description="JWT Secret from the Supabase project"
    )
    UPSTASH_REDIS_URL: str = Field(
        min_length=1, description="Upstash Redis instance URL"
    )
    UPSTASH_REDIS_TOKEN: str = Field(
        min_length=1, description="Upstash Redis auth token"
    )
    SUPABASE_SERVICE_ROLE: str = Field(
        min_length=1, description="Service Role from the Supabase project"
    )
    GROQ_API_KEY: str = Field(
        min_length=1, description="Groq API key — used for ASR, LLM and TTS"
    )
    TTS_BUCKET: str = Field(
        min_length=1, description="Supabase Storage bucket for TTS audio"
    )
    LESSONS_BUCKET: str = Field(
        min_length=1, description="Supabase Storage bucket for lesson JSONs"
    )
    LLM_MODEL: str = Field(
        min_length=1, description="Groq model used for the pedagogical agent"
    )

    # K-07.2 — /turn stability under load (all overridable via env)
    MAX_AUDIO_BYTES: int = Field(
        default=5_242_880, gt=0, description="Max audio upload size for /turn (5 MB)"
    )
    MAX_CONCURRENT_TURNS: int = Field(
        default=16, gt=0, description="Max /turn requests processed concurrently"
    )
    TURN_QUEUE_TIMEOUT_SECONDS: float = Field(
        default=5.0, gt=0, description="Max wait for a /turn slot before 503"
    )
    RATE_LIMIT_TURNS_PER_MINUTE: int = Field(
        default=12, gt=0, description="Per-user /turn requests allowed per minute"
    )

    # K-07.3 — telemetry ingestion
    TELEMETRY_MAX_BATCH: int = Field(
        default=50, gt=0, description="Max telemetry events accepted per request"
    )

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )


settings = Settings()
