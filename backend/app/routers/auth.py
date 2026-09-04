from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token, UserRole
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings
from app.dependencies.auth import get_current_user, require_role

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_token(email: str, password: str, db: Session):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": create_access_token(
            subject=str(user.id),
            expires_delta=access_token_expires,
        ),
        "token_type": "bearer",
    }

@router.post("/register", response_model=UserResponse)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """Registers a new user."""
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    hashed_password = get_password_hash(user_in.password)
    
    # role is an Enum, we store it in lowercase to maintain DB consistency
    db_user = User(
        name=user_in.name,
        email=user_in.email,
        password=hashed_password,
        role=user_in.role.value.lower()
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/login", response_model=Token)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    """Authenticates a user and returns a JWT token."""
    return _issue_token(user_in.email, user_in.password, db)


@router.post("/token", response_model=Token)
def oauth2_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """OAuth2 password-form endpoint used by Swagger UI and OAuth2 clients."""
    return _issue_token(form_data.username, form_data.password, db)

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Retrieves the authenticated user's profile."""
    return current_user

@router.get("/test", dependencies=[Depends(require_role(UserRole.ADMINISTRATOR))])
def test_rbac(current_user: User = Depends(get_current_user)):
    """
    Temporary endpoint to test RBAC and Authentication flow.
    Only accessible by users with the ADMINISTRATOR role.
    """
    return {
        "message": "You have administrator access!",
        "user_id": current_user.id,
        "role": current_user.role
    }
