from fastapi import FastAPI

from app.core.auth import AuthUser

from app.routers.conversation import router as conversation_router



app = FastAPI(title="Kotoba Backend", version="0.1.0")
app.include_router(conversation_router)

@app.get("/health")
async def health():
    return {"status": "ok"}

#This endpoit will be removed later on 
#And It will be moved to his own router
@app.get("/v1/me")
async def user_profile(auth_user: AuthUser):
    return auth_user

