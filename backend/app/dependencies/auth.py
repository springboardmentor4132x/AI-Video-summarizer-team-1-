from typing import Union, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.schemas.user import UserRole
from app.db.session import get_db
from app.models.user import User

# Pretend the login endpoint is at /auth/login for OpenAPI/Swagger scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_db)
) -> User:
    """
    Extracts the JWT token, verifies it, and returns the authenticated user identity from the database.
    Returns 401 if the token is missing, invalid, expired, or the user is not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception
        
    try:
        user_id = int(user_id_str)
    except ValueError:
        raise credentials_exception
        
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
        
    return user

def require_role(allowed_roles: Union[UserRole, List[UserRole]]):
    """
    Dependency factory to check if the current user has the required role.
    Usage: Depends(require_role(UserRole.ADMINISTRATOR))
       or: Depends(require_role([UserRole.EDUCATOR, UserRole.CONTENT_CREATOR]))
    """
    if isinstance(allowed_roles, UserRole) or isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]
        
    def role_checker(current_user: User = Depends(get_current_user)):
        # Normalize the database string role to Title Case to compare with UserRole Enum
        user_role_normalized = current_user.role.title() if isinstance(current_user.role, str) else current_user.role
        
        try:
            # Safely attempt to parse as UserRole
            enum_role = UserRole(user_role_normalized)
        except ValueError:
            # If the database contains an invalid role not in our Enum
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted"
            )
            
        if enum_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted"
            )
        return current_user
    
    return role_checker
