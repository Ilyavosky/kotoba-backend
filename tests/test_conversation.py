"""
Integration tests: POST /v1/conversation/turn

Covers:
  - Happy path: valid audio + valid token → 200 + correct JSON fields
  - ASR failure: Groq raises exception → 502
  - LLM failure: reserved for when LLM stage is implemented → 502
"""

import io
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.core.deps import get_groq_client
from app.main import app

# ── Test constants ────────────────────────────────────────────────────────────

TEST_SECRET = "test-secret-only-for-pytest-never-use-in-prod!"
TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_EMAIL = "ilya@kotoba.test"
TEST_LESSON_ID = "lesson-001"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_token(
    *,
    secret: str = TEST_SECRET,
    user_id: str = TEST_USER_ID,
    email: str = TEST_EMAIL,
    audience: str = "authenticated",
    exp_offset: int = 3600,
) -> str:
    """Builds a signed JWT with the given parameters."""
    now = int(datetime.now(UTC).timestamp())
    return jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "role": "authenticated",
            "aud": audience,
            "iat": now,
            "exp": now + exp_offset,
        },
        secret,
        algorithm="HS256",
    )


def _auth_headers(token: str | None = None) -> dict:
    t = token or _make_token()
    return {"Authorization": f"Bearer {t}"}


def _fake_audio() -> bytes:
    """Returns minimal bytes that satisfy the UploadFile field."""
    return b"RIFF\x00\x00\x00\x00WAVEfmt "


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.core.config as config_module
    monkeypatch.setattr(config_module.settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def mock_groq_success() -> MagicMock:
    """Groq client whose ASR call returns a transcription."""
    groq = MagicMock()
    transcription_result = MagicMock()
    transcription_result.text = "hola, ¿cómo estás?"
    groq.audio.transcriptions.create.return_value = transcription_result
    return groq


@pytest.fixture()
def mock_groq_asr_failure() -> MagicMock:
    """Groq client whose ASR call raises an exception."""
    groq = MagicMock()
    groq.audio.transcriptions.create.side_effect = Exception(
        "Groq ASR unavailable"
    )
    return groq


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_conversation_turn_success(
    client: TestClient,
    mock_groq_success: MagicMock,
) -> None:
    """Happy path: valid audio + valid JWT → 200 with expected JSON fields."""
    app.dependency_overrides[get_groq_client] = lambda: mock_groq_success
    try:
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={"audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")},
            data={"lesson_id": TEST_LESSON_ID},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["transcription"] == "hola, ¿cómo estás?"
    assert "agent_response" in body
    assert "audio_url" in body


def test_conversation_turn_requires_auth(client: TestClient) -> None:
    """No Authorization header → 401 before even reaching the service."""
    response = client.post(
        "/v1/conversation/turn",
        files={"audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")},
        data={"lesson_id": TEST_LESSON_ID},
    )
    assert response.status_code == 401


def test_conversation_turn_asr_failure_returns_502(
    client: TestClient,
    mock_groq_asr_failure: MagicMock,
) -> None:
    """ASR stage raises → endpoint must return 502, not 500."""
    app.dependency_overrides[get_groq_client] = lambda: mock_groq_asr_failure
    try:
        response = client.post(
            "/v1/conversation/turn",
            headers=_auth_headers(),
            files={"audio_file": ("audio.webm", io.BytesIO(_fake_audio()), "audio/webm")},
            data={"lesson_id": TEST_LESSON_ID},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
