from sqlalchemy.orm import Session

from sqlalchemy import or_

from app.models.learning import ClassroomMember, ClassroomResource, SharedSummary
from app.models.video import Video


def learner_has_shared_access(db: Session, video_id: int, learner_id: int) -> bool:
    public_share = db.query(SharedSummary.id).filter(SharedSummary.video_id == video_id, SharedSummary.audience == "students").first()
    if public_share is not None:
        return True
    return db.query(ClassroomResource.id).join(ClassroomMember, ClassroomMember.classroom_id == ClassroomResource.classroom_id).filter(
        ClassroomResource.resource_type == "video", ClassroomResource.resource_id == video_id, ClassroomMember.learner_id == learner_id
    ).first() is not None


def learner_accessible_videos(db: Session, learner_id: int):
    shared_video_ids = db.query(SharedSummary.video_id).filter(SharedSummary.audience == "students").distinct()
    classroom_video_ids = db.query(ClassroomResource.resource_id).join(ClassroomMember, ClassroomMember.classroom_id == ClassroomResource.classroom_id).filter(
        ClassroomResource.resource_type == "video", ClassroomMember.learner_id == learner_id
    )
    return db.query(Video).filter(or_(Video.id.in_(shared_video_ids), Video.id.in_(classroom_video_ids)), Video.status == "completed")
