"""Analytics router providing owner-scoped and platform-wide analytics."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_role
from app.models.user import User
from app.schemas.analytics import AnalyticsDashboard
from app.schemas.user import UserRole
from app.services.analytics import build_dashboard

router = APIRouter(tags=["analytics"])


@router.get("/admin/analytics", response_model=AnalyticsDashboard)
def get_admin_analytics(
    current_user: User = Depends(require_role(UserRole.ADMINISTRATOR)),
    db: Session = Depends(get_db),
    date_from: Optional[date] = Query(default=None, alias="from"),
    date_to: Optional[date] = Query(default=None, alias="to"),
) -> AnalyticsDashboard:
    """Return platform-wide aggregate analytics. Accessible only by Administrators."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The 'from' date must not be after the 'to' date",
        )
    return build_dashboard(db, date_from=date_from, date_to=date_to)


@router.get("/analytics", response_model=AnalyticsDashboard)
def get_creator_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    date_from: Optional[date] = Query(default=None, alias="from"),
    date_to: Optional[date] = Query(default=None, alias="to"),
) -> AnalyticsDashboard:
    """Return owner-scoped analytics limited to the authenticated creator's videos."""
    user_role_normalized = current_user.role.title() if isinstance(current_user.role, str) else current_user.role
    if user_role_normalized not in ("Content Creator", "Administrator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only content creators or administrators can access analytics",
        )
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The 'from' date must not be after the 'to' date",
        )
    # If Administrator calls /analytics without /admin, or Content Creator calls it:
    # Scope to current_user.id for Content Creator
    user_id = current_user.id if user_role_normalized == "Content Creator" else None
    return build_dashboard(db, user_id=user_id, date_from=date_from, date_to=date_to)
