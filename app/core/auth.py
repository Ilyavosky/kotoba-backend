from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.core.config import settings
from app.schemas.user import CurrentUser

_bearer = HTTPBearer(auto_error=False)

async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )
    try:
        payload = jwt.decode(credentials.credentials, settings.SUPABASE_JWT_SECRET, algorithms=['HS256'])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )
    return CurrentUser.model_validate(payload)

from typing import Annotated

AuthUser = Annotated[CurrentUser, Depends(get_current_user)]