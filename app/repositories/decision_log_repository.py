import asyncio
from datetime import datetime, timezone
from typing import Literal

import structlog
from supabase import Client

class DecisionLogRepository:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def log_decision(
        self,
        user_id: str,
        lesson_id: str,
        step_before: int,
        step_after: int,
        decision: Literal["advance", "stay_clean", "stay_error"],
        error_detected: str | None,
        full_reasoning: dict[str, object],
    ) -> None:
        
        payload = {
            "user_id": user_id,
            "lesson_id": lesson_id,
            "step_before": step_before,
            "step_after": step_after,
            "decision": decision,
            "error_detected": error_detected,
            "full_reasoning": full_reasoning,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            await asyncio.to_thread(
                lambda: self._client.table("decision_logs")
                .insert(payload)
                .execute()
            )
        except Exception:
            structlog.get_logger().warning("decision_log_insert_failed", user_id=user_id, lesson_id=lesson_id)