"""JWT creation and decoding helpers."""

from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt

from app.config import settings
from app.models import User


def create_access_token(user: User) -> str:
    """Create a signed access token containing non-sensitive user claims."""

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iat": now,
        "exp": expires_at,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, object]:
    """Decode and validate a signed access token."""

    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "access":
        raise JWTError("Invalid token type")
    if not payload.get("sub"):
        raise JWTError("Token subject is missing")
    return payload


def token_subject(payload: dict[str, object]) -> int:
    """Parse the integer user ID from a validated token payload."""

    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise JWTError("Token subject is invalid")
    try:
        return int(subject)
    except ValueError as exc:
        raise JWTError("Token subject is invalid") from exc
