from pydantic import BaseModel, EmailStr, Field, field_validator
from enum import Enum
from datetime import datetime

class UserRole(str, Enum):
    CONTENT_CREATOR = "Content Creator"
    LEARNER = "Learner"
    EDUCATOR = "Educator"
    ADMINISTRATOR = "Administrator"

class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    role: UserRole

    @field_validator('role', mode='before')
    @classmethod
    def normalize_role(cls, v):
        if isinstance(v, str):
            return v.title()
        return v

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: int
    created_at: datetime
    
    model_config = {"from_attributes": True}

class Token(BaseModel):
    access_token: str
    token_type: str
