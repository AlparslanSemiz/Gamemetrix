from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from ..config import get_settings
from ..rate_limit import limiter
from ..security import AuthenticatedUser, create_access_token, verify_admin_password
from ..services.admin_audit import record_login_attempt


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
@limiter.limit(get_settings().AUTH_RATE_LIMIT)
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> TokenResponse:
    if len(form_data.username) > 64 or len(form_data.password) > 128:
        record_login_attempt(request, form_data.username, status.HTTP_401_UNAUTHORIZED)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
    if not verify_admin_password(form_data.username, form_data.password):
        record_login_attempt(request, form_data.username, status.HTTP_401_UNAUTHORIZED)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        AuthenticatedUser(username=form_data.username, role="admin")
    )
    record_login_attempt(request, form_data.username, status.HTTP_200_OK)
    return TokenResponse(
        access_token=token,
        expires_in=get_settings().JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
