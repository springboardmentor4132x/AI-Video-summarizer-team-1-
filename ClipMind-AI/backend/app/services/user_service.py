"""User registration database operations."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.models import User
from app.schemas.auth import RegistrationRequest


class DuplicateEmailError(Exception):
    """Raised when an email is already registered."""


class InvalidCredentialsError(Exception):
    """Raised when login credentials do not match an account."""


ROLE_NAMES = (
    "Content Creator",
    "Learner",
    "Educator",
    "Administrator",
)


def register_user(db: Session, registration: RegistrationRequest) -> User:
    """Create a user after validating email uniqueness and resolving its role."""

    normalized_email = str(registration.email).lower()
    existing_user = db.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    if existing_user is not None:
        raise DuplicateEmailError

    user = User(
        full_name=registration.full_name,
        email=normalized_email,
        password_hash=hash_password(registration.password),
        role=registration.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateEmailError from exc

    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    """Find a user and verify its password, returning generic failures."""

    user = db.scalar(
        select(User).where(func.lower(User.email) == email.lower())
    )
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError
    return user
