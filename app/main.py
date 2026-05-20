from fastapi import FastAPI
from app.core.auth import AuthUser

app = FastAPI(title="Kotoba Backend", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/v1/me")
async def user_profile(auth_user: AuthUser):
    return auth_user