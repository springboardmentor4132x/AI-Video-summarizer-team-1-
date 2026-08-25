from fastapi import APIRouter, Depends
from app.dependencies.auth import get_current_user, require_role, TempUser
from app.schemas.user import UserRole

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/test", dependencies=[Depends(require_role(UserRole.ADMINISTRATOR))])
def test_rbac(current_user: TempUser = Depends(get_current_user)):
    """
    Temporary endpoint to test RBAC and Authentication flow.
    Only accessible by users with the ADMINISTRATOR role.
    """
    return {
        "message": "You have administrator access!",
        "user_id": current_user.id,
        "role": current_user.role
    }
