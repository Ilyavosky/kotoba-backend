from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings
from app.schemas.user import CurrentUser

# We use Auto_error=False so it lets us return 401 instead of FastAPI's default 403
_bearer = HTTPBearer(auto_error=False)


# Async function created to get the current user, checks the credentials using
# the fastapi security HTTAuthorizationCredentials in order to check if the JWT is valid
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )
    try:
        # Stores the validation in the payload variable where
        # It uses python jose to decode the jwt body
        payload = jwt.decode(
            credentials.credentials,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        ) from err
    # This function uses the CurrentUser class
    # And validates the attributes with pydantic
    return CurrentUser.model_validate(payload)


AuthUser = Annotated[CurrentUser, Depends(get_current_user)]
