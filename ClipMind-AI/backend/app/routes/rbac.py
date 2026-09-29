"""Example endpoints used to verify Module 1 role-based access."""

from fastapi import APIRouter, Depends

from app.auth.authorization import Permission, require_permissions
from app.models import User


router = APIRouter(prefix="/rbac", tags=["authorization"])


@router.get("/creator/uploads")
def creator_upload_access(
    user: User = Depends(require_permissions(Permission.UPLOAD_VIDEOS)),
) -> dict[str, str]:
    """Verify access to creator video-upload functionality."""

    return {"message": f"Upload access granted for {user.role}"}


@router.get("/creator/history")
def creator_history_access(
    user: User = Depends(require_permissions(Permission.VIEW_UPLOAD_HISTORY)),
) -> dict[str, str]:
    """Verify access to creator upload history functionality."""

    return {"message": f"Upload history access granted for {user.role}"}


@router.get("/learner/content")
def learner_content_access(
    user: User = Depends(require_permissions(Permission.ACCESS_LEARNER_CONTENT)),
) -> dict[str, str]:
    """Verify access to learner-related content."""

    return {"message": f"Learner content access granted for {user.role}"}


@router.get("/educator/content")
def educator_content_access(
    user: User = Depends(require_permissions(Permission.MANAGE_EDUCATIONAL_CONTENT)),
) -> dict[str, str]:
    """Verify access to educational content management."""

    return {"message": f"Educational content access granted for {user.role}"}


@router.get("/admin/users")
def administrator_user_access(
    user: User = Depends(require_permissions(Permission.MANAGE_USERS)),
) -> dict[str, str]:
    """Verify access to administrative user management."""

    return {"message": f"User management access granted for {user.role}"}


@router.get("/admin/platform")
def administrator_platform_access(
    user: User = Depends(require_permissions(Permission.MONITOR_PLATFORM_ACTIVITY)),
) -> dict[str, str]:
    """Verify access to administrative platform monitoring."""

    return {"message": f"Platform monitoring access granted for {user.role}"}
