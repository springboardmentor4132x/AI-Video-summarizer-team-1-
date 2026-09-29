"""Reusable role-based authorization dependencies."""

from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.models import User


class Permission(StrEnum):
    """Business capabilities that can be assigned to roles."""

    UPLOAD_VIDEOS = "upload_videos"
    MANAGE_UPLOADED_VIDEOS = "manage_uploaded_videos"
    VIEW_UPLOAD_HISTORY = "view_upload_history"
    VIEW_AVAILABLE_CONTENT = "view_available_content"
    ACCESS_LEARNER_CONTENT = "access_learner_content"
    UPLOAD_LECTURE_VIDEOS = "upload_lecture_videos"
    MANAGE_EDUCATIONAL_CONTENT = "manage_educational_content"
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    MONITOR_PLATFORM_ACTIVITY = "monitor_platform_activity"
    MANAGE_UPLOADED_CONTENT = "manage_uploaded_content"
    ACCESS_ADMIN_FUNCTIONALITY = "access_administrative_functionality"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "Content Creator": frozenset(
        {
            Permission.UPLOAD_VIDEOS,
            Permission.MANAGE_UPLOADED_VIDEOS,
            Permission.VIEW_UPLOAD_HISTORY,
        }
    ),
    "Learner": frozenset(
        {
            Permission.VIEW_AVAILABLE_CONTENT,
            Permission.ACCESS_LEARNER_CONTENT,
        }
    ),
    "Educator": frozenset(
        {
            Permission.UPLOAD_LECTURE_VIDEOS,
            Permission.MANAGE_EDUCATIONAL_CONTENT,
        }
    ),
    "Administrator": frozenset(Permission),
}


def permissions_for_role(role_name: str) -> frozenset[Permission]:
    """Return the capabilities for a role, or no capabilities for an unknown role."""

    return ROLE_PERMISSIONS.get(role_name, frozenset())


def has_permission(user: User, permission: Permission) -> bool:
    """Check a user's database-backed role against one capability."""

    return permission in permissions_for_role(user.role)


def require_permissions(*required_permissions: Permission) -> Callable[..., User]:
    """Create a dependency requiring all listed permissions."""

    if not required_permissions:
        raise ValueError("At least one permission is required")

    def permission_dependency(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if not all(has_permission(user, permission) for permission in required_permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )
        return user

    return permission_dependency


def require_any_permission(*allowed_permissions: Permission) -> Callable[..., User]:
    """Create a dependency requiring at least one listed capability."""

    if not allowed_permissions:
        raise ValueError("At least one permission is required")

    def permission_dependency(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if not any(has_permission(user, permission) for permission in allowed_permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to upload videos",
            )
        return user

    return permission_dependency
