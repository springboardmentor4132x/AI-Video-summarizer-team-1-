"""Authentication request and response schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


AllowedRole = Literal[
    "Content Creator",
    "Learner",
    "Educator",
    "Administrator",
]


class RegistrationRequest(BaseModel):
    """Payload required to create a user account."""

    full_name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    role: AllowedRole

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Full name is required")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> EmailStr:
        return str(value).lower()

    @model_validator(mode="after")
    def validate_password_confirmation(self) -> "RegistrationRequest":
        if self.password != self.confirm_password:
            raise ValueError("Password and confirm_password must match")
        return self


class LoginRequest(BaseModel):
    """Credentials required to obtain an access token."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> EmailStr:
        return str(value).lower()


class RegistrationResponse(BaseModel):
    """Safe representation returned after registration."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    """JWT response returned after successful login."""

    access_token: str
    token_type: str
    expires_in: int
    user_id: str
    email: EmailStr
    role: str


class CurrentUserResponse(BaseModel):
    """Safe authenticated-user response."""

    id: int
    full_name: str
    email: EmailStr
    role: str
    created_at: datetime
