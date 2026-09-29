"""Administrator analytics route."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
import logging

from app.auth.authorization import Permission, require_permissions
from app.auth.dependencies import CurrentUser
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas.analytics import AnalyticsAIResponse, AnalyticsDashboard
from app.services.analytics import build_dashboard
from app.services.analytics_ai import build_ai_analytics_snapshot, generate_analytics_ai_insights


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["analytics"])
creator_router = APIRouter(prefix="/analytics", tags=["analytics"])


def _build_ai_analytics_response(
    db: Session,
    user_id: int | None,
    date_from: date | None,
    date_to: date | None,
) -> AnalyticsAIResponse:
    analytics = build_dashboard(db, user_id=user_id, date_from=date_from, date_to=date_to)
    snapshot = build_ai_analytics_snapshot(analytics)
    try:
        insights = generate_analytics_ai_insights(snapshot)
    except Exception as exc:
        logger.warning(
            "Analytics AI insight generation failed operation=analytics_ai_insights "
            "model=%s exception_type=%s status_code=%s provider_status=%s final_reason=%s",
            (settings.gemini_model or "gemini-2.5-flash").strip() or "gemini-2.5-flash",
            type(exc).__name__,
            getattr(exc, "code", getattr(exc, "status_code", None)),
            getattr(exc, "status", None),
            getattr(exc, "reason", None),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI insights are temporarily unavailable. Your analytics data is still available.",
        ) from exc
    return AnalyticsAIResponse(analytics=analytics, ai_insights=insights)


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


@router.post("/analytics/ai-insights", response_model=AnalyticsAIResponse)
def administrator_analytics_ai_insights(
    _user: User = Depends(require_permissions(Permission.MONITOR_PLATFORM_ACTIVITY)),
    db: Session = Depends(get_db),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
) -> AnalyticsAIResponse:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="The 'from' date must not be after the 'to' date")
    return _build_ai_analytics_response(db, None, date_from, date_to)


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


@creator_router.post("/ai-insights", response_model=AnalyticsAIResponse)
def creator_analytics_ai_insights(
    user: CurrentUser,
    db: Session = Depends(get_db),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
) -> AnalyticsAIResponse:
    if user.role != "Content Creator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only content creators can access owner-scoped analytics",
        )
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="The 'from' date must not be after the 'to' date")
    return _build_ai_analytics_response(db, user.id, date_from, date_to)