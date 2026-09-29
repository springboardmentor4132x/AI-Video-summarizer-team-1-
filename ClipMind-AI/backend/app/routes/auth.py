"""Authentication-related API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.jwt import create_access_token
from app.config import settings
from app.database import get_db
from app.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    RegistrationRequest,
    RegistrationResponse,
    TokenResponse,
)
from app.services.user_service import (
    DuplicateEmailError,
    InvalidCredentialsError,
    authenticate_user,
    register_user,
)


router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(registration: RegistrationRequest, db: Session = Depends(get_db)) -> RegistrationResponse:
    """Register a user account without creating an authentication session."""

    try:
        user = register_user(db, registration)
    except DuplicateEmailError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    return RegistrationResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
    )


@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Verify credentials and return a signed access token."""

    try:
        user = authenticate_user(db, str(credentials.email), credentials.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return TokenResponse(
        access_token=create_access_token(user),
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        user_id=str(user.id),
        email=user.email,
        role=user.role,
    )


@router.get("/me", response_model=CurrentUserResponse)
def current_user(user: CurrentUser) -> CurrentUserResponse:
    """Return the authenticated user's safe profile."""

    return CurrentUserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
    )
