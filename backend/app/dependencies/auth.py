from typing import Union, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from app.core.security import decode_access_token
from app.schemas.user import UserRole

# Pretend the login endpoint is at /login for OpenAPI/Swagger scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# TEMPORARY MOCK USER CLASS
# Represents the authenticated user until the actual DB User model is implemented by Member 2.
class TempUser(BaseModel):
    id: int
    email: str
    role: UserRole

async def get_current_user(token: str = Depends(oauth2_scheme)) -> TempUser:
    """
    Extracts the JWT token, verifies it, and returns the authenticated user identity.
    Returns 401 if the token is missing, invalid, or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 1 & 2: Extract and verify JWT
    payload = decode_access_token(token)
    
    # 3: Reject invalid/expired tokens
    if payload is None:
        raise credentials_exception
    
    # 4: Extract the user identity
    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception
        
    # --- FUTURE DB INTEGRATION POINT ---
    # When Member 2 finishes the PostgreSQL User model and DB Session setup, replace this mock with:
    # 
    # db_session = next(get_db())
    # user = db_session.query(User).filter(User.id == int(user_id_str)).first()
    # if user is None:
    #     raise credentials_exception
    # return user
    # -----------------------------------
    
    # 5: Return temporary identity
    try:
        # For testing RBAC, we extract 'role' from the JWT payload if present.
        # Otherwise, default to LEARNER.
        role_value = payload.get("role", UserRole.LEARNER)
        role = UserRole(role_value)
        user_id = int(user_id_str)
        return TempUser(id=user_id, email=f"user{user_id}@example.com", role=role)
    except ValueError:
        # Will trigger if user_id is not int or role is invalid according to Enum
        raise credentials_exception

def require_role(allowed_roles: Union[UserRole, List[UserRole]]):
    """
    Dependency factory to check if the current user has the required role.
    Usage: Depends(require_role(UserRole.ADMINISTRATOR))
       or: Depends(require_role([UserRole.EDUCATOR, UserRole.CONTENT_CREATOR]))
    """
    if isinstance(allowed_roles, UserRole) or isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]
        
    def role_checker(current_user: TempUser = Depends(get_current_user)):
        # Separation of Concerns: Authentication is already done by get_current_user.
        # This function only performs Authorization.
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted"
            )
        return current_user
    
    return role_checker
