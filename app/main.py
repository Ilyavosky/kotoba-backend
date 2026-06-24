from fastapi import FastAPI

from app.core.auth import AuthUser
from app.core.logging import configure_logging
from app.core.redis import lifespan
from app.middleware.logging import RequestLoggingMiddleware
from app.routers.conversation import router as conversation_router
from app.routers.lessons import router as lessons_router
from app.schemas.user import CurrentUser

configure_logging()
app = FastAPI(title="Kotoba Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)
app.include_router(conversation_router)
app.include_router(lessons_router)

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# This endpoit will be removed later on
# And It will be moved to his own router
@app.get("/v1/me")
async def user_profile(auth_user: AuthUser) -> CurrentUser:
    return auth_user
