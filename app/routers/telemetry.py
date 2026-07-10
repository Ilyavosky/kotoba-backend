import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import AuthUser
from app.core.config import settings
from app.core.deps import get_telemetry_repository
from app.repositories.telemetry_repository import TelemetryRepository
from app.schemas.telemetry import TelemetryBatchIn, TelemetryIngestResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/telemetry", tags=["telemetry"])


@router.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TelemetryIngestResponse,
)
async def ingest_events(
    batch: TelemetryBatchIn,
    user: AuthUser,
    repository: TelemetryRepository = Depends(get_telemetry_repository),
) -> TelemetryIngestResponse:
    if len(batch.events) > settings.TELEMETRY_MAX_BATCH:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Batch too large, max {settings.TELEMETRY_MAX_BATCH} "
                "events per request"
            ),
        )

    try:
        await repository.insert_events(user.user_id, batch.events)
    except Exception as e:
        # 502 so the client can retry with the same batch — telemetry is
        # non-critical for the student, but silently dropping it would
        # corrupt the beta analytics (K-04) without anyone noticing.
        logger.warning("telemetry_insert_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Telemetry storage unavailable",
        ) from e

    return TelemetryIngestResponse(accepted=len(batch.events))
