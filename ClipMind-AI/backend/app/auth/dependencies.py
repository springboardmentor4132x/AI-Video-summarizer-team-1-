"""Reusable authentication dependencies for protected endpoints."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import decode_access_token, token_subject
from app.database import get_db
from app.models import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def credentials_exception() -> HTTPException:
    """Create the standard bearer authentication failure response."""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Decode the bearer token and load its current database user."""

    try:
        payload = decode_access_token(token)
        user_id = token_subject(payload)
    except (JWTError, ValueError):
        raise credentials_exception()

    user = db.scalar(
        select(User).where(User.id == user_id)
    )
    if user is None:
        raise credentials_exception()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
