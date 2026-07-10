"""
K-07.2 — Load test for POST /v1/conversation/turn.

Runs the real ASGI app in-process with the external services mocked
(Groq ASR/LLM/TTS and Supabase replaced by fakes with simulated latency),
fires N concurrent virtual users and reports latency percentiles and
status-code counts. No network, no API quota, reproducible.

The capacity limiter, rate limiter (permissive here), auth, routing and
orchestration code paths are the REAL ones — that is what we measure.

Usage:
    uv run python scripts/load_test_turn.py --users 20 --turns 5
    MAX_CONCURRENT_TURNS=8 uv run python scripts/load_test_turn.py --users 50
"""

import argparse
import asyncio
import os
import statistics
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load test for /turn")
    parser.add_argument("--users", type=int, default=20, help="concurrent users")
    parser.add_argument("--turns", type=int, default=5, help="turns per user")
    parser.add_argument("--asr-ms", type=int, default=300, help="simulated ASR ms")
    parser.add_argument("--llm-ms", type=int, default=800, help="simulated LLM ms")
    parser.add_argument("--tts-ms", type=int, default=400, help="simulated TTS ms")
    return parser.parse_args()


def _ensure_env() -> None:
    """Provide dummy env vars so Settings loads without a .env file."""
    defaults = {
        "SUPABASE_URL": "https://load-test.supabase.co",
        "SUPABASE_ANON_KEY": "load-test",
        "SUPABASE_JWT_SECRET": "load-test-secret",
        "UPSTASH_REDIS_URL": "redis://localhost:6379",
        "UPSTASH_REDIS_TOKEN": "load-test",
        "SUPABASE_SERVICE_ROLE": "load-test",
        "GROQ_API_KEY": "load-test",
        "TTS_BUCKET": "load-test",
        "LESSONS_BUCKET": "load-test",
        "LLM_MODEL": "load-test",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


TEST_SECRET = "load-test-secret-never-use-in-prod"
LESSON_ID = "lesson-load-001"


def _make_token(user_id: str) -> str:
    from jose import jwt

    now = int(datetime.now(UTC).timestamp())
    return str(jwt.encode(
        {
            "sub": user_id,
            "email": f"{user_id[:8]}@load.test",
            "role": "authenticated",
            "aud": "authenticated",
            "iat": now,
            "exp": now + 3600,
        },
        TEST_SECRET,
        algorithm="HS256",
    ))


def _build_overrides(app: Any, args: argparse.Namespace) -> None:
    """Replace every external dependency with a latency-simulating fake."""
    from app.core.deps import (
        get_agent_service,
        get_decision_engine_service,
        get_groq_client,
        get_lesson_repository,
        get_module_repository,
        get_rate_limiter,
        get_redis_repository,
        get_tts_service,
    )
    from app.repositories.decision_log_repository import DecisionLogRepository
    from app.repositories.step_state_repository import StepStateRepository
    from app.repositories.student_progress_repository import StudentProgressRepository
    from app.schemas.domain import StepState
    from app.services.decision_engine import DecisionEngineService

    # ASR: sync sleep inside the mock -- exercises the real to_thread path
    groq = MagicMock()
    transcription = MagicMock()
    transcription.text = "hola, quiero comprar un boleto"

    def _slow_asr(**_: Any) -> Any:
        time.sleep(args.asr_ms / 1000)
        return transcription

    groq.audio.transcriptions.create.side_effect = _slow_asr

    lesson_repo = MagicMock()
    lesson_repo.get_lesson = AsyncMock(
        return_value={"numero": "2", "titulo": "Transportation"}
    )

    async def _slow_llm(**_: Any) -> tuple[str, dict[str, Any]]:
        await asyncio.sleep(args.llm_ms / 1000)
        return "Great! Can you say it again?", {
            "paso_aplicado": "4",
            "error_detectado": None,
        }

    agent = MagicMock()
    agent.generate_response = AsyncMock(side_effect=_slow_llm)

    async def _slow_tts(_: str) -> str:
        await asyncio.sleep(args.tts_ms / 1000)
        return "https://load.test/audio.mp3"

    tts = MagicMock()
    tts.synthesize = AsyncMock(side_effect=_slow_tts)

    # In-memory Redis-style history repo
    history: dict[str, list[dict[str, str]]] = {}

    async def _get_history(user_id: str, lesson_id: str) -> list[dict[str, str]]:
        return history.get(f"{user_id}:{lesson_id}", [])

    async def _append_turn(
        user_id: str, lesson_id: str, user_message: str, agent_response: str
    ) -> None:
        key = f"{user_id}:{lesson_id}"
        history.setdefault(key, []).append(
            {"rol": "estudiante", "contenido": user_message}
        )
        history[key].append({"rol": "agente", "contenido": agent_response})

    redis_repo = MagicMock()
    redis_repo.get_history = AsyncMock(side_effect=_get_history)
    redis_repo.append_turn = AsyncMock(side_effect=_append_turn)

    # REAL decision engine over in-memory fakes -- exercises the actual
    # progression logic on every turn
    step_states: dict[str, StepState] = {}

    step_repo = MagicMock(spec=StepStateRepository)
    step_repo.get_step_state = AsyncMock(
        side_effect=lambda u, le: step_states.get(f"{u}:{le}")
    )

    async def _save_state(user_id: str, lesson_id: str, state: StepState) -> None:
        step_states[f"{user_id}:{lesson_id}"] = state

    step_repo.save_step_state = AsyncMock(side_effect=_save_state)

    progress_repo = MagicMock(spec=StudentProgressRepository)
    progress_repo.get_progress = AsyncMock(return_value=None)
    progress_repo.upsert_progress = AsyncMock(return_value=None)

    log_repo = MagicMock(spec=DecisionLogRepository)
    log_repo.log_decision = AsyncMock(return_value=None)

    engine = DecisionEngineService(step_repo, progress_repo, log_repo)

    module_repo = MagicMock()
    module_repo.get_next_lesson_id = AsyncMock(return_value=None)

    # Permissive rate limiter: we measure capacity, not throttling
    limiter = MagicMock()
    limiter.check = AsyncMock(return_value=None)

    app.dependency_overrides[get_groq_client] = lambda: groq
    app.dependency_overrides[get_lesson_repository] = lambda: lesson_repo
    app.dependency_overrides[get_agent_service] = lambda: agent
    app.dependency_overrides[get_tts_service] = lambda: tts
    app.dependency_overrides[get_redis_repository] = lambda: redis_repo
    app.dependency_overrides[get_decision_engine_service] = lambda: engine
    app.dependency_overrides[get_module_repository] = lambda: module_repo
    app.dependency_overrides[get_rate_limiter] = lambda: limiter


def _percentile(sorted_ms: list[float], pct: float) -> float:
    if not sorted_ms:
        return 0.0
    idx = min(int(len(sorted_ms) * pct / 100), len(sorted_ms) - 1)
    return sorted_ms[idx]


async def _run(args: argparse.Namespace) -> None:
    import httpx

    import app.core.config as config_module
    from app.main import app

    config_module.settings.SUPABASE_JWT_SECRET = TEST_SECRET
    _build_overrides(app, args)

    results: list[tuple[int, float]] = []
    audio = b"RIFF" + b"\x00" * 2048

    async def virtual_user(client: httpx.AsyncClient) -> None:
        user_id = str(uuid.uuid4())
        token = _make_token(user_id)
        for _ in range(args.turns):
            t0 = time.perf_counter()
            response = await client.post(
                "/v1/conversation/turn",
                headers={"Authorization": f"Bearer {token}"},
                files={"audio_file": ("a.webm", audio, "audio/webm")},
                data={"lesson_id": LESSON_ID},
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            results.append((response.status_code, elapsed_ms))

    transport = httpx.ASGITransport(app=app)
    t_start = time.perf_counter()
    async with httpx.AsyncClient(
        transport=transport, base_url="http://load.test", timeout=60.0
    ) as client:
        await asyncio.gather(*(virtual_user(client) for _ in range(args.users)))
    wall_s = time.perf_counter() - t_start

    ok = sorted(ms for status, ms in results if status == 200)
    by_status: dict[int, int] = {}
    for status, _ in results:
        by_status[status] = by_status.get(status, 0) + 1

    from app.core.config import settings

    print("\n=== K-07.2 load test: POST /v1/conversation/turn ===")
    print(
        f"users={args.users} turns/user={args.turns} "
        f"total={len(results)} wall={wall_s:.1f}s "
        f"throughput={len(results) / wall_s:.1f} req/s"
    )
    print(
        f"simulated latencies: ASR={args.asr_ms}ms LLM={args.llm_ms}ms "
        f"TTS={args.tts_ms}ms | MAX_CONCURRENT_TURNS={settings.MAX_CONCURRENT_TURNS}"
    )
    print(f"status codes: {by_status}")
    if ok:
        print(
            f"latency 200s (ms): p50={_percentile(ok, 50):.0f} "
            f"p95={_percentile(ok, 95):.0f} p99={_percentile(ok, 99):.0f} "
            f"min={ok[0]:.0f} max={ok[-1]:.0f} mean={statistics.mean(ok):.0f}"
        )
    error_rate = 100 * (len(results) - len(ok)) / len(results) if results else 0.0
    print(f"non-200 rate: {error_rate:.1f}%")


def main() -> None:
    args = _parse_args()
    _ensure_env()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
