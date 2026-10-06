from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_role
from app.models.learning import AuditLog, Classroom, ClassroomMember, ClassroomResource, LearningBookmark, LearningHistory, LearningMaterial, PlatformSetting, SharedSummary
from app.models.summary import SummaryStatus
from app.models.user import User
from app.models.video import Video
from app.schemas.learning import BookmarkCreate, ClassroomCreate, ClassroomJoin, ClassroomResourceCreate, HistoryUpdate, MaterialCreate, ShareCreate
from app.schemas.user import UserRole
from app.dependencies.video_access import learner_accessible_videos, learner_has_shared_access

router = APIRouter(tags=["learning"])


def _completed_video(video_id: int, db: Session) -> Video:
    video = db.query(Video).filter(Video.id == video_id, Video.status == "completed").first()
    if video is None:
        raise HTTPException(status_code=404, detail="Completed video not found")
    return video


@router.get("/learning/content")
def learning_content(db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.LEARNER))):
    return learner_accessible_videos(db, current_user.id).order_by(Video.uploaded_at.desc()).all()


@router.get("/learning/materials")
def shared_learning_materials(db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.LEARNER))):
    shared_video_ids = db.query(SharedSummary.video_id).filter(SharedSummary.audience == "students").distinct()
    class_material_ids = db.query(ClassroomResource.resource_id).join(ClassroomMember, ClassroomMember.classroom_id == ClassroomResource.classroom_id).filter(ClassroomResource.resource_type == "material", ClassroomMember.learner_id == _.id)
    return db.query(LearningMaterial).filter(
        (LearningMaterial.video_id.in_(shared_video_ids)) | (LearningMaterial.id.in_(class_material_ids))
    ).order_by(LearningMaterial.created_at.desc()).all()


@router.get("/learning/history")
def get_learning_history(db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.LEARNER))):
    return db.query(LearningHistory).filter(LearningHistory.user_id == current_user.id).order_by(LearningHistory.viewed_at.desc()).all()


@router.post("/learning/history/{video_id}")
def update_learning_history(video_id: int, payload: HistoryUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.LEARNER))):
    if not learner_has_shared_access(db, video_id, current_user.id):
        raise HTTPException(status_code=404, detail="Shared video not found")
    video = _completed_video(video_id, db)
    item = db.query(LearningHistory).filter(LearningHistory.user_id == current_user.id, LearningHistory.video_id == video_id).first()
    if item is None:
        item = LearningHistory(user_id=current_user.id, video_id=video_id)
        db.add(item)
    item.last_position_seconds = payload.position_seconds
    item.watch_duration_seconds = (item.watch_duration_seconds or 0) + payload.watched_seconds
    if video.duration_seconds and video.duration_seconds > 0:
        item.completion_percentage = min(100.0, round(payload.position_seconds / video.duration_seconds * 100, 2))
    db.commit()
    db.refresh(item)
    return item


@router.get("/learning/bookmarks")
def get_bookmarks(db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.LEARNER))):
    return db.query(LearningBookmark).filter(LearningBookmark.user_id == current_user.id).order_by(LearningBookmark.created_at.desc()).all()


@router.post("/learning/bookmarks", status_code=status.HTTP_201_CREATED)
def add_bookmark(payload: BookmarkCreate, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.LEARNER))):
    if not learner_has_shared_access(db, payload.video_id, current_user.id):
        raise HTTPException(status_code=404, detail="Shared video not found")
    video = _completed_video(payload.video_id, db)
    if payload.key_moment_id is not None:
        moment = next((moment for moment in video.key_moments if moment.id == payload.key_moment_id), None)
        if moment is None:
            raise HTTPException(status_code=404, detail="Key moment not found")
    item = db.query(LearningBookmark).filter_by(user_id=current_user.id, video_id=payload.video_id, key_moment_id=payload.key_moment_id, kind=payload.kind).first()
    if item is None:
        item = LearningBookmark(user_id=current_user.id, **payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
    return item


@router.delete("/learning/bookmarks/{bookmark_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_bookmark(bookmark_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.LEARNER))):
    item = db.query(LearningBookmark).filter(LearningBookmark.id == bookmark_id, LearningBookmark.user_id == current_user.id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    db.delete(item)
    db.commit()


@router.post("/educator/materials", status_code=status.HTTP_201_CREATED)
def create_material(payload: MaterialCreate, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    video = db.query(Video).filter(Video.id == payload.video_id, Video.user_id == current_user.id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    material = LearningMaterial(educator_id=current_user.id, **payload.model_dump())
    db.add(material)
    db.add(AuditLog(actor_id=current_user.id, action="educator.material.create", resource=f"video:{video.id}"))
    db.commit()
    db.refresh(material)
    return material


@router.get("/educator/materials")
def list_materials(db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    return db.query(LearningMaterial).filter(LearningMaterial.educator_id == current_user.id).order_by(LearningMaterial.created_at.desc()).all()


@router.put("/educator/materials/{material_id}")
def update_material(material_id: int, payload: MaterialCreate, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    material = db.query(LearningMaterial).filter(LearningMaterial.id == material_id, LearningMaterial.educator_id == current_user.id).first()
    if material is None:
        raise HTTPException(status_code=404, detail="Learning material not found")
    video = db.query(Video).filter(Video.id == payload.video_id, Video.user_id == current_user.id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    material.video_id = payload.video_id
    material.title = payload.title
    material.content = payload.content
    db.add(AuditLog(actor_id=current_user.id, action="educator.material.update", resource=f"material:{material.id}"))
    db.commit()
    db.refresh(material)
    return material


@router.delete("/educator/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(material_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    material = db.query(LearningMaterial).filter(LearningMaterial.id == material_id, LearningMaterial.educator_id == current_user.id).first()
    if material is None:
        raise HTTPException(status_code=404, detail="Learning material not found")
    db.add(AuditLog(actor_id=current_user.id, action="educator.material.delete", resource=f"material:{material.id}"))
    db.delete(material)
    db.commit()


@router.post("/educator/shares", status_code=status.HTTP_201_CREATED)
def share_summary(payload: ShareCreate, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    video = db.query(Video).filter(Video.id == payload.video_id, Video.user_id == current_user.id).first()
    if video is None or video.transcript is None or video.transcript.summary is None or video.transcript.summary.status != SummaryStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="A completed summary is required before sharing")
    share = db.query(SharedSummary).filter_by(educator_id=current_user.id, video_id=payload.video_id, audience=payload.audience).first()
    if share is not None:
        return share
    share = SharedSummary(educator_id=current_user.id, **payload.model_dump())
    db.add(share)
    db.add(AuditLog(actor_id=current_user.id, action="share_summary", resource=f"video:{video.id}"))
    db.commit()
    db.refresh(share)
    return share


@router.get("/educator/shares")
def list_shares(db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    return db.query(SharedSummary).filter(SharedSummary.educator_id == current_user.id).order_by(SharedSummary.created_at.desc()).all()


@router.get("/educator/analytics")
def educator_analytics(db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    videos = db.query(Video).filter(Video.user_id == current_user.id).order_by(Video.uploaded_at.desc()).all()
    shared_ids = {row[0] for row in db.query(SharedSummary.video_id).filter(SharedSummary.educator_id == current_user.id).all()}
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    per_video = []
    all_history = []
    for video in videos:
        history = db.query(LearningHistory).filter(LearningHistory.video_id == video.id).all()
        all_history.extend(history)
        per_video.append({
            "video_id": video.id,
            "filename": video.filename,
            "published": video.id in shared_ids,
            "views": len(history),
            "unique_learners": len({item.user_id for item in history}),
            "watch_time_seconds": sum(item.watch_duration_seconds or 0 for item in history),
            "average_completion_percentage": round(sum(item.completion_percentage or 0 for item in history) / len(history), 2) if history else None,
        })
    return {
        "total_lectures": len(videos),
        "published_lectures": len(shared_ids),
        "total_views": len(all_history),
        "unique_learners": len({item.user_id for item in all_history}),
        "active_learners_30d": len({item.user_id for item in all_history if item.viewed_at and item.viewed_at.replace(tzinfo=timezone.utc) >= cutoff}),
        "watch_time_seconds": sum(item.watch_duration_seconds or 0 for item in all_history),
        "average_completion_percentage": round(sum(item.completion_percentage or 0 for item in all_history) / len(all_history), 2) if all_history else None,
        "per_video": per_video,
    }


def _owned_classroom(classroom_id: int, db: Session, educator: User) -> Classroom:
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id, Classroom.educator_id == educator.id).first()
    if classroom is None:
        raise HTTPException(status_code=404, detail="Classroom not found")
    return classroom


@router.post("/educator/classrooms", status_code=status.HTTP_201_CREATED)
def create_classroom(payload: ClassroomCreate, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    classroom = Classroom(educator_id=current_user.id, invite_code=token_urlsafe(9), **payload.model_dump())
    db.add(classroom)
    db.add(AuditLog(actor_id=current_user.id, action="classroom.create", resource="classroom:new"))
    db.commit()
    db.refresh(classroom)
    return classroom


@router.get("/educator/classrooms")
def list_educator_classrooms(db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    return db.query(Classroom).filter(Classroom.educator_id == current_user.id).order_by(Classroom.created_at.desc()).all()


@router.put("/educator/classrooms/{classroom_id}")
def update_classroom(classroom_id: int, payload: ClassroomCreate, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    classroom = _owned_classroom(classroom_id, db, current_user)
    classroom.name = payload.name
    classroom.description = payload.description
    db.add(AuditLog(actor_id=current_user.id, action="classroom.update", resource=f"classroom:{classroom.id}"))
    db.commit()
    db.refresh(classroom)
    return classroom


@router.delete("/educator/classrooms/{classroom_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_classroom(classroom_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    classroom = _owned_classroom(classroom_id, db, current_user)
    db.add(AuditLog(actor_id=current_user.id, action="classroom.delete", resource=f"classroom:{classroom.id}"))
    db.delete(classroom)
    db.commit()


@router.get("/educator/classrooms/{classroom_id}/members")
def list_classroom_members(classroom_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    _owned_classroom(classroom_id, db, current_user)
    return [
        {"id": member.id, "learner_id": member.learner_id, "name": learner.name, "email": learner.email, "joined_at": member.joined_at}
        for member, learner in db.query(ClassroomMember, User).join(User, User.id == ClassroomMember.learner_id).filter(ClassroomMember.classroom_id == classroom_id).order_by(ClassroomMember.joined_at.desc()).all()
    ]


@router.delete("/educator/classrooms/{classroom_id}/members/{learner_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_classroom_member(classroom_id: int, learner_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    _owned_classroom(classroom_id, db, current_user)
    member = db.query(ClassroomMember).filter(ClassroomMember.classroom_id == classroom_id, ClassroomMember.learner_id == learner_id).first()
    if member is None:
        raise HTTPException(status_code=404, detail="Classroom member not found")
    db.delete(member)
    db.commit()


@router.post("/educator/classrooms/{classroom_id}/resources", status_code=status.HTTP_201_CREATED)
def share_classroom_resource(classroom_id: int, payload: ClassroomResourceCreate, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    _owned_classroom(classroom_id, db, current_user)
    if payload.resource_type == "video":
        resource = db.query(Video).filter(Video.id == payload.resource_id, Video.user_id == current_user.id, Video.status == "completed").first()
    else:
        resource = db.query(LearningMaterial).filter(LearningMaterial.id == payload.resource_id, LearningMaterial.educator_id == current_user.id).first()
    if resource is None:
        raise HTTPException(status_code=404, detail="Owned classroom resource not found")
    item = db.query(ClassroomResource).filter_by(classroom_id=classroom_id, resource_type=payload.resource_type, resource_id=payload.resource_id).first()
    if item is None:
        item = ClassroomResource(classroom_id=classroom_id, shared_by=current_user.id, **payload.model_dump())
        db.add(item)
        db.add(AuditLog(actor_id=current_user.id, action="classroom.resource.share", resource=f"classroom:{classroom_id}:{payload.resource_type}:{payload.resource_id}"))
        db.commit()
        db.refresh(item)
    return item


@router.get("/educator/classrooms/{classroom_id}/resources")
def list_educator_classroom_resources(classroom_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    _owned_classroom(classroom_id, db, current_user)
    items = db.query(ClassroomResource).filter(ClassroomResource.classroom_id == classroom_id).order_by(ClassroomResource.created_at.desc()).all()
    output = []
    for item in items:
        resource = db.query(Video).filter(Video.id == item.resource_id).first() if item.resource_type == "video" else db.query(LearningMaterial).filter(LearningMaterial.id == item.resource_id).first()
        output.append({"id": item.id, "resource_type": item.resource_type, "resource_id": item.resource_id, "resource": resource})
    return output


@router.delete("/educator/classrooms/{classroom_id}/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_classroom_resource(classroom_id: int, resource_id: int, resource_type: str, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    _owned_classroom(classroom_id, db, current_user)
    item = db.query(ClassroomResource).filter_by(classroom_id=classroom_id, resource_id=resource_id, resource_type=resource_type).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Classroom resource not found")
    db.delete(item)
    db.commit()


@router.get("/educator/classrooms/{classroom_id}/analytics")
def classroom_analytics(classroom_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    _owned_classroom(classroom_id, db, current_user)
    video_ids = [row[0] for row in db.query(ClassroomResource.resource_id).filter(ClassroomResource.classroom_id == classroom_id, ClassroomResource.resource_type == "video").all()]
    videos = db.query(Video).filter(Video.id.in_(video_ids)).all() if video_ids else []
    learner_ids = [row[0] for row in db.query(ClassroomMember.learner_id).filter(ClassroomMember.classroom_id == classroom_id).all()]
    history = db.query(LearningHistory).filter(
        LearningHistory.video_id.in_(video_ids),
        LearningHistory.user_id.in_(learner_ids),
    ).all() if video_ids and learner_ids else []
    return {
        "classroom_id": classroom_id,
        "learners": db.query(ClassroomMember).filter(ClassroomMember.classroom_id == classroom_id).count(),
        "views": len(history),
        "unique_viewers": len({item.user_id for item in history}),
        "watch_time_seconds": sum(item.watch_duration_seconds or 0 for item in history),
        "average_completion_percentage": round(sum(item.completion_percentage or 0 for item in history) / len(history), 2) if history else None,
        "per_video": [{"video_id": video.id, "filename": video.filename, "views": sum(1 for item in history if item.video_id == video.id), "watch_time_seconds": sum(item.watch_duration_seconds or 0 for item in history if item.video_id == video.id), "average_completion_percentage": round(sum(item.completion_percentage or 0 for item in history if item.video_id == video.id) / sum(1 for item in history if item.video_id == video.id), 2) if any(item.video_id == video.id for item in history) else None} for video in videos],
    }


@router.get("/learner/classrooms")
def list_learner_classrooms(db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.LEARNER))):
    return db.query(Classroom).join(ClassroomMember).filter(ClassroomMember.learner_id == current_user.id).order_by(Classroom.created_at.desc()).all()


@router.post("/learner/classrooms/join", status_code=status.HTTP_201_CREATED)
def join_classroom(payload: ClassroomJoin, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.LEARNER))):
    classroom = db.query(Classroom).filter(Classroom.invite_code == payload.invite_code.strip()).first()
    if classroom is None:
        raise HTTPException(status_code=404, detail="Classroom invite code was not found")
    member = db.query(ClassroomMember).filter_by(classroom_id=classroom.id, learner_id=current_user.id).first()
    if member is None:
        member = ClassroomMember(classroom_id=classroom.id, learner_id=current_user.id)
        db.add(member)
        db.commit()
        db.refresh(member)
    return {"classroom": classroom, "membership": member}


@router.get("/learner/classrooms/{classroom_id}/resources")
def list_learner_classroom_resources(classroom_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.LEARNER))):
    membership = db.query(ClassroomMember).filter_by(classroom_id=classroom_id, learner_id=current_user.id).first()
    if membership is None:
        raise HTTPException(status_code=404, detail="Classroom not found")
    items = db.query(ClassroomResource).filter(ClassroomResource.classroom_id == classroom_id).all()
    output = []
    for item in items:
        row = db.query(Video).filter(Video.id == item.resource_id, Video.status == "completed").first() if item.resource_type == "video" else db.query(LearningMaterial).filter(LearningMaterial.id == item.resource_id).first()
        if row is not None:
            output.append({"id": item.id, "resource_type": item.resource_type, "resource_id": item.resource_id, "resource": row})
    return output


@router.delete("/educator/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(share_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.EDUCATOR))):
    share = db.query(SharedSummary).filter(SharedSummary.id == share_id, SharedSummary.educator_id == current_user.id).first()
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    db.add(AuditLog(actor_id=current_user.id, action="educator.summary.revoke", resource=f"video:{share.video_id}"))
    db.delete(share)
    db.commit()


@router.get("/admin/audit-logs")
def audit_logs(db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.ADMINISTRATOR))):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(500).all()


@router.get("/admin/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.ADMINISTRATOR))):
    return db.query(PlatformSetting).order_by(PlatformSetting.key).all()


@router.put("/admin/settings/{key}")
def update_setting(key: str, value: str, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.ADMINISTRATOR))):
    setting = db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
    if setting is None:
        setting = PlatformSetting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
    db.add(AuditLog(actor_id=current_user.id, action="update_setting", resource=f"setting:{key}"))
    db.commit()
    db.refresh(setting)
    return setting
