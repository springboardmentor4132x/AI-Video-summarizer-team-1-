"""Administrator analytics route."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.authorization import Permission, require_permissions
from app.auth.dependencies import CurrentUser
from app.database import get_db
from app.models import User
from app.schemas.analytics import AnalyticsDashboard
from app.services.analytics import build_dashboard


router = APIRouter(prefix="/admin", tags=["analytics"])
creator_router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/analytics", response_model=AnalyticsDashboard)
def administrator_analytics(
    _user: User = Depends(require_permissions(Permission.MONITOR_PLATFORM_ACTIVITY)),
    db: Session = Depends(get_db),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
) -> AnalyticsDashboard:
    """Return aggregate platform analytics without exposing sensitive user fields."""

    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="The 'from' date must not be after the 'to' date")
    return build_dashboard(db, date_from=date_from, date_to=date_to)


@creator_router.get("", response_model=AnalyticsDashboard)
def creator_analytics(
    user: CurrentUser,
    db: Session = Depends(get_db),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
) -> AnalyticsDashboard:
    """Return analytics limited to videos owned by the authenticated creator."""

    if user.role != "Content Creator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only content creators can access owner-scoped analytics",
        )
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="The 'from' date must not be after the 'to' date")
    return build_dashboard(db, user_id=user.id, date_from=date_from, date_to=date_to)