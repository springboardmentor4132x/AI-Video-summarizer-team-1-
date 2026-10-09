"""Admin-only endpoints for the ClipMind AI platform."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_role
from app.models.video import Video
from app.schemas.user import UserRole
from app.schemas.video import VideoResponse


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)


@router.get(
    "/upload-history",
    response_model=list[VideoResponse],
    dependencies=[Depends(require_role(UserRole.ADMINISTRATOR))],
)
def get_admin_upload_history(
    db: Session = Depends(get_db),
):
    """Return upload history for all users on the platform.

    Accessible by Administrators only.  Results are ordered most-recent first,
    matching the ordering used by the per-user ``/videos/history`` endpoint.
    """
    return (
        db.query(Video)
        .order_by(Video.uploaded_at.desc())
        .all()
    )
