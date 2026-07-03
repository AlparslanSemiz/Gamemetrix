from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from ..config import get_settings
from ..rate_limit import limiter
from ..security import AuthenticatedUser, create_access_token, verify_admin_password


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
    if not verify_admin_password(form_data.username, form_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        AuthenticatedUser(username=form_data.username, role="admin")
    )
    return TokenResponse(
        access_token=token,
        expires_in=get_settings().JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
