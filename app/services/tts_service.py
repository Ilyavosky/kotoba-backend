import asyncio
import logging
import uuid
from typing import Any

from groq import Groq
from supabase import Client

logger = logging.getLogger(__name__)

_TTS_MODEL = "playai-tts"
_TTS_VOICE = "Fritz-PlayAI"
_TTS_FORMAT = "mp3"
_SIGNED_URL_TTL = 3600  # 1 hour


class TtsService:
    def __init__(self, groq_client: Groq, supabase_client: Client, bucket: str) -> None:
        self._groq = groq_client
        self._supabase = supabase_client
        self._bucket = bucket

    async def synthesize(self, text: str) -> str | None:
        """
        Converts text to audio and returns a signed Supabase URL (TTL 1h).
        Returns None if anything fails — the conversation flow must not be interrupted.
        """
        if not text or not text.strip():
            return None

        try:
            audio_bytes = await asyncio.to_thread(self._call_groq_tts, text)
        except Exception as e:
            logger.error("tts_groq_error: %s", e)
            return None

        try:
            url = await asyncio.to_thread(self._upload_and_sign, audio_bytes)
            logger.info("tts_ok url=%s", url[:60])
            return url
        except Exception as e:
            logger.error("tts_supabase_error: %s", e)
            return None

    def _call_groq_tts(self, text: str) -> bytes:
        response = self._groq.audio.speech.create(
            model=_TTS_MODEL,
            voice=_TTS_VOICE,
            input=text[:4000],
            response_format=_TTS_FORMAT,
        )
        return response.read()

    def _upload_and_sign(self, audio_bytes: bytes) -> str:
        filename = f"tts/{uuid.uuid4()}.mp3"

        self._supabase.storage.from_(self._bucket).upload(
            path=filename,
            file=audio_bytes,
            file_options={"content-type": "audio/mpeg"},
        )

        result: dict[str, Any] = self._supabase.storage.from_(
            self._bucket
        ).create_signed_url(path=filename, expires_in=_SIGNED_URL_TTL)

        return str(result["signedURL"])
