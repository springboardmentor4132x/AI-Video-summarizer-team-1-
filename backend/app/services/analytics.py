"""Read-only analytics queries over existing ClipMind data."""

import re
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import KeyMoment, Summary, Transcript, UploadHistory, User, Video
from app.schemas.analytics import (
    ActivityItem,
    AIInsight,
    AnalyticsDashboard,
    ContentInsights,
    CountItem,
    KeywordItem,
    KeyMomentAnalytics,
    KeywordIntelligence,
    OverviewAnalytics,
    PipelineStage,
    ProcessingInsights,
    RecentActivity,
    RecentKeyMoment,
    RecentSummary,
    RecentVideo,
    ScoreComponent,
    SummaryReports,
    TranscriptInsights,
    TopicInsight,
    IntelligenceScore,
    UsageAnalytics,
    VideoAnalytics,
)

STOP_WORDS = {
    "about", "after", "again", "against", "all", "also", "and", "are", "because", "been",
    "being", "but", "can", "could", "for", "from", "have", "how", "into", "just", "more",
    "most", "not", "our", "out", "over", "same", "should", "some", "such", "than", "that",
    "the", "their", "there", "these", "they", "this", "those", "through", "under", "was",
    "were", "what", "when", "where", "which", "while", "with", "would", "you", "your", "then",
    "them", "here", "his", "her", "its", "in", "is", "it", "of", "on", "to", "a", "an", "as",
    "at", "by", "or", "be", "do", "um", "uh", "like", "okay", "right", "yeah", "well",
}
PROCESSING_STATUSES = ("PROCESSING", "VALIDATING", "FFMPEG_PROCESSING", "READY_FOR_AI", "AI_PROCESSING")
PENDING_STATUSES = ("UPLOADING", "UPLOADED")


def _value(value) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _count_items(rows) -> list[CountItem]:
    return [CountItem(label=_value(label), count=int(count)) for label, count in rows]


def _word_count(text: str | None) -> int:
    if not text:
        return 0
    return len(re.findall(r"\b\w+(?:['’-]\w+)*\b", text, flags=re.UNICODE))


def _keywords(texts: list[str]) -> list[KeywordItem]:
    counts = Counter()
    for text in texts:
        for word in re.findall(r"\b\w+(?:['’-]\w+)*\b", text.casefold(), flags=re.UNICODE):
            if len(word) < 3 or word.isnumeric() or word in STOP_WORDS:
                continue
            counts[word] += 1
    return [
        KeywordItem(keyword=word, count=count, frequency=count, rank=index)
        for index, (word, count) in enumerate(counts.most_common(10), start=1)
    ]


def _date_bounds(date_from, date_to, rows):
    dates = [day for day, _ in rows if day is not None]
    return date_from or (min(dates) if dates else None), date_to or (max(dates) if dates else None)


def _fill_activity(rows, date_from, date_to) -> list[ActivityItem]:
    normalized = [
        (date.fromisoformat(day) if isinstance(day, str) else day, int(count))
        for day, count in rows
        if day is not None
    ]
    start, end = _date_bounds(date_from, date_to, normalized)
    if start is None or end is None or start > end:
        return []
    counts = dict(normalized)
    return [
        ActivityItem(
            date=(start + timedelta(days=offset)).isoformat(),
            count=counts.get(start + timedelta(days=offset), 0),
        )
        for offset in range((end - start).days + 1)
    ]


def _range_conditions(column, date_from, date_to):
    conditions = []
    if date_from is not None:
        conditions.append(column >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to is not None:
        conditions.append(column < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc))
    return conditions


def _pipeline_stage(count: int, denominator: int) -> PipelineStage:
    return PipelineStage(count=count, coverage_percentage=round(count / denominator * 100, 2) if denominator else 0)


def _tokens(text: str | None) -> list[str]:
    if not text:
        return []
    return [
        word
        for word in re.findall(r"\b\w+(?:['’-]\w+)*\b", text.casefold(), flags=re.UNICODE)
        if len(word) >= 3 and not word.isnumeric() and word not in STOP_WORDS
    ]


def _summary_text(summary: Summary | None) -> str:
    if summary is None:
        return ""
    return " ".join(filter(None, [summary.content, summary.overview, *(summary.main_points or []), *(summary.key_takeaways or [])]))


def _video_score(video: Video) -> tuple[float, list[ScoreComponent]]:
    """Score content completeness: processing 25%, transcript 25%, summary 20%, moments 15%, richness 15%."""
    transcript = video.transcript
    summary = video.summary
    moments = video.key_moments
    transcript_words = _word_count(transcript.text if transcript else None)
    summary_words = _word_count(_summary_text(summary))
    processing = 100 if _value(video.processing_status) == "COMPLETED" else 55 if _value(video.processing_status) in PROCESSING_STATUSES else 20 if _value(video.processing_status) in PENDING_STATUSES else 0
    transcript_score = 100 if transcript and _value(transcript.status) == "COMPLETED" else 50 if transcript else 0
    transcript_score = min(transcript_score, round(transcript_words / 5)) if transcript_words else 0
    summary_score = 100 if summary and _value(summary.status) == "COMPLETED" else 45 if summary else 0
    summary_score = min(summary_score, 100 if summary_words >= 40 else round(summary_words / 40 * 100)) if summary_words else 0
    moment_score = min(100, len(moments) * 20) if _value(video.processing_status) == "COMPLETED" else 0
    richness_score = min(100, len(set(_tokens(transcript.text if transcript else ""))) * 8 + min(transcript_words, 500) / 10)
    components = [
        ScoreComponent(label="Processing", score=processing, weight=0.25),
        ScoreComponent(label="Transcript", score=transcript_score, weight=0.25),
        ScoreComponent(label="Summary", score=summary_score, weight=0.20),
        ScoreComponent(label="Key moments", score=moment_score, weight=0.15),
        ScoreComponent(label="Content richness", score=round(richness_score, 2), weight=0.15),
    ]
    return round(sum(component.score * component.weight for component in components), 2), components


def _score_explanation(score: float, videos: int, transcripts: int, summaries: int, moments: int) -> str:
    if not videos:
        return "Upload a video to begin building content intelligence."
    strength = "Strong" if score >= 75 else "Developing" if score >= 45 else "Early"
    return f"{strength} coverage across {videos} videos: {transcripts} transcripts, {summaries} summaries, and {moments} detected key moments."


def _in_date_range(value: datetime | None, date_from: date | None, date_to: date | None) -> bool:
    if value is None:
        return False
    value_date = value.date()
    return (date_from is None or value_date >= date_from) and (date_to is None or value_date <= date_to)


def build_dashboard(db: Session, user_id: int | None = None, date_from: date | None = None, date_to: date | None = None) -> AnalyticsDashboard:
    """Build platform or owner-scoped analytics with SQL-applied date filters."""
    video_conditions = ([Video.user_id == user_id] if user_id is not None else []) + _range_conditions(Video.uploaded_at, date_from, date_to)
    video_count = db.scalar(select(func.count(Video.id)).where(*video_conditions)) or 0
    status_rows = db.execute(select(Video.processing_status, func.count(Video.id)).where(*video_conditions).group_by(Video.processing_status)).all()
    status_counts = {_value(status): int(count) for status, count in status_rows}
    completed_videos = status_counts.get("COMPLETED", 0)
    failed_videos = status_counts.get("FAILED", 0)
    processing_videos = sum(status_counts.get(status, 0) for status in PROCESSING_STATUSES)
    uploaded_videos = sum(status_counts.get(status, 0) for status in PENDING_STATUSES)
    total_duration = db.scalar(select(func.coalesce(func.sum(Video.duration_seconds), 0)).where(*video_conditions)) or 0
    average_duration = db.scalar(select(func.coalesce(func.avg(Video.duration_seconds), 0)).where(*video_conditions)) or 0
    upload_rows = db.execute(select(func.date(Video.uploaded_at), func.count(Video.id)).where(*video_conditions).group_by(func.date(Video.uploaded_at)).order_by(func.date(Video.uploaded_at))).all()

    history_conditions = ([Video.user_id == user_id] if user_id is not None else []) + _range_conditions(UploadHistory.uploaded_at, date_from, date_to)
    processing_rows = db.execute(
        select(func.date(UploadHistory.uploaded_at), func.count(UploadHistory.id))
        .join(Video, Video.id == UploadHistory.video_id)
        .where(*history_conditions)
        .where(UploadHistory.status.in_((*PROCESSING_STATUSES, "COMPLETED", "FAILED")))
        .group_by(func.date(UploadHistory.uploaded_at))
        .order_by(func.date(UploadHistory.uploaded_at))
    ).all()

    recent_video_rows = db.execute(
        select(Video, User.full_name)
        .options(selectinload(Video.transcript), selectinload(Video.summary), selectinload(Video.key_moments))
        .join(User, User.id == Video.user_id)
        .where(*video_conditions).order_by(Video.uploaded_at.desc())
    ).all()

    transcript_conditions = ([Video.user_id == user_id] if user_id is not None else []) + _range_conditions(Transcript.created_at, date_from, date_to)
    transcript_rows = db.scalars(select(Transcript).join(Video, Video.id == Transcript.video_id).where(*transcript_conditions)).all()
    transcript_texts = [transcript.text or "" for transcript in transcript_rows]
    transcript_word_counts = [_word_count(text) for text in transcript_texts]
    transcript_characters = sum(len(text) for text in transcript_texts)
    total_transcripts = len(transcript_rows)
    total_transcript_words = sum(transcript_word_counts)

    summary_conditions = ([Video.user_id == user_id] if user_id is not None else []) + _range_conditions(Summary.created_at, date_from, date_to)
    summary_rows = db.scalars(select(Summary).join(Video, Video.id == Summary.video_id).where(*summary_conditions)).all()
    summary_texts = [" ".join(filter(None, [summary.content, summary.overview, *(summary.main_points or []), *(summary.key_takeaways or [])])) for summary in summary_rows]
    summary_word_counts = [_word_count(text) for text in summary_texts]
    total_summaries = len(summary_rows)
    completed_summaries = sum(_value(summary.status) == "COMPLETED" for summary in summary_rows)
    videos_with_summaries = len({summary.video_id for summary in summary_rows})
    summary_characters = sum(len(text) for text in summary_texts)
    recent_summary_rows = db.execute(select(Summary, Video.filename).join(Video, Video.id == Summary.video_id).where(*summary_conditions).order_by(Summary.created_at.desc()).limit(20)).all()

    moment_conditions = ([Video.user_id == user_id] if user_id is not None else []) + _range_conditions(KeyMoment.created_at, date_from, date_to)
    moment_rows = db.scalars(select(KeyMoment).join(Video, Video.id == KeyMoment.video_id).where(*moment_conditions)).all()
    total_key_moments = len(moment_rows)
    videos_with_key_moments = len({moment.video_id for moment in moment_rows})
    moment_duration = sum(max(0, moment.end_time - moment.start_time) for moment in moment_rows)
    importance_scores = [moment.importance_score for moment in moment_rows]
    recent_moment_rows = db.execute(select(KeyMoment, Video.filename).join(Video, Video.id == KeyMoment.video_id).where(*moment_conditions).order_by(KeyMoment.importance_score.desc(), KeyMoment.created_at.desc()).limit(20)).all()
    moments_by_video = Counter(moment.video_id for moment in moment_rows)
    video_names = dict(db.execute(
        select(Video.id, Video.filename)
        .where(Video.id.in_(list(moments_by_video)))
    ).all()) if moments_by_video else {}
    grouped_moments = [CountItem(label=video_names.get(video_id, str(video_id)), count=count) for video_id, count in moments_by_video.most_common()]

    total_users = 0 if user_id is not None else (db.scalar(select(func.count(User.id))) or 0)
    role_rows = [] if user_id is not None else db.execute(select(User.role, func.count(User.id)).group_by(User.role).order_by(User.role)).all()

    keyword_counts = Counter()
    keyword_video_ids: dict[str, set[str]] = {}
    topic_moment_counts = Counter()
    topic_summary_counts = Counter()
    for transcript in transcript_rows:
        video_id = str(transcript.video_id)
        for token in _tokens(transcript.text):
            keyword_counts[token] += 1
            keyword_video_ids.setdefault(token, set()).add(video_id)
    for moment in moment_rows:
        if moment.topic:
            topic = moment.topic.casefold().strip()
            if topic:
                topic_moment_counts[topic] += 1
                keyword_video_ids.setdefault(topic, set()).add(str(moment.video_id))
    for summary in summary_rows:
        for token in _tokens(_summary_text(summary)):
            topic_summary_counts[token] += 1

    keyword_total = sum(keyword_counts.values())
    keyword_intelligence = [
        KeywordIntelligence(
            keyword=word,
            frequency=count,
            share_percentage=round(count / keyword_total * 100, 2) if keyword_total else 0,
            video_count=len(keyword_video_ids.get(word, set())),
        )
        for word, count in keyword_counts.most_common(20)
    ]
    top_topics = [
        TopicInsight(
            topic=word,
            percentage=round(count / keyword_total * 100, 2) if keyword_total else 0,
            frequency=count,
            video_count=len(keyword_video_ids.get(word, set())),
            related_keywords=[word],
            key_moment_count=topic_moment_counts.get(word, 0),
            summary_count=topic_summary_counts.get(word, 0),
        )
        for word, count in keyword_counts.most_common(10)
    ]

    content_activity_counts: dict[str, dict[str, int]] = {}
    for transcript in transcript_rows:
        day = transcript.created_at.date().isoformat()
        content_activity_counts.setdefault(day, {"transcripts": 0, "summaries": 0, "key_moments": 0})["transcripts"] += 1
    for summary in summary_rows:
        day = summary.created_at.date().isoformat()
        content_activity_counts.setdefault(day, {"transcripts": 0, "summaries": 0, "key_moments": 0})["summaries"] += 1
    for moment in moment_rows:
        day = moment.created_at.date().isoformat()
        content_activity_counts.setdefault(day, {"transcripts": 0, "summaries": 0, "key_moments": 0})["key_moments"] += 1
    content_activity = [
        {"date": day, **counts}
        for day, counts in sorted(content_activity_counts.items())
    ]
    average_transcript_words = total_transcript_words / total_transcripts if total_transcripts else 0
    total_summary_words = sum(summary_word_counts)
    average_summary_words = total_summary_words / total_summaries if total_summaries else 0
    importance_buckets = {"Low (0.00-0.33)": [], "Medium (0.34-0.66)": [], "High (0.67-1.00)": []}
    for moment in moment_rows:
        bucket = "Low (0.00-0.33)" if moment.importance_score <= 0.33 else "Medium (0.34-0.66)" if moment.importance_score <= 0.66 else "High (0.67-1.00)"
        importance_buckets[bucket].append(moment.importance_score)
    importance_distribution = [
        {"label": label, "count": len(scores), "average_importance": round(sum(scores) / len(scores), 2) if scores else 0}
        for label, scores in importance_buckets.items()
    ]

    video_intelligence: list[RecentVideo] = []
    score_values: list[float] = []
    score_components: list[list[ScoreComponent]] = []
    for video, owner_name in recent_video_rows:
        transcript = video.transcript
        summary = video.summary
        moments = video.key_moments
        score, components = _video_score(video)
        score_values.append(score)
        score_components.append(components)
        transcript_tokens = _tokens(transcript.text if transcript else "")
        video_topics = list(dict.fromkeys(transcript_tokens))[:10]
        importance_scores_for_video = [moment.importance_score for moment in moments]
        video_intelligence.append(RecentVideo(
            id=str(video.id), filename=video.filename, owner_name=owner_name,
            status=_value(video.processing_status), uploaded_at=video.uploaded_at,
            duration_seconds=video.duration_seconds,
            transcript_status=_value(transcript.status) if transcript else None,
            summary_status=_value(summary.status) if summary else None,
            key_moment_count=len(moments),
            transcript_word_count=_word_count(transcript.text if transcript else None),
            transcript_character_count=len(transcript.text or "") if transcript else 0,
            summary_word_count=_word_count(_summary_text(summary)),
            topic_count=len(video_topics),
            top_topics=video_topics,
            top_keywords=video_topics[:5],
            ai_score=score,
            ai_score_components={component.label: component.score for component in components},
            average_importance=round(sum(importance_scores_for_video) / len(importance_scores_for_video), 2) if importance_scores_for_video else 0,
            highest_importance=max(importance_scores_for_video, default=0),
            main_points_count=len(summary.main_points or []) if summary else 0,
            key_takeaways_count=len(summary.key_takeaways or []) if summary else 0,
        ))

    activity = []
    for video, owner_name in recent_video_rows[:20]:
        transcript = video.transcript
        summary = video.summary
        moment_count = len(video.key_moments)
        activity.append(RecentActivity(type="VIDEO_UPLOADED", timestamp=video.uploaded_at, video_id=str(video.id), video_name=video.filename, description=f"{video.filename} was uploaded"))
        if _value(video.processing_status) == "COMPLETED" and _in_date_range(video.updated_at, date_from, date_to):
            activity.append(RecentActivity(type="VIDEO_COMPLETED", timestamp=video.updated_at, video_id=str(video.id), video_name=video.filename, description=f"{video.filename} finished processing"))
        if transcript and _value(transcript.status) == "COMPLETED" and _in_date_range(transcript.created_at, date_from, date_to):
            activity.append(RecentActivity(type="TRANSCRIPT_GENERATED", timestamp=transcript.created_at, video_id=str(video.id), video_name=video.filename, description=f"Transcript generated for {video.filename}"))
        if summary and _value(summary.status) == "COMPLETED" and _in_date_range(summary.created_at, date_from, date_to):
            activity.append(RecentActivity(type="SUMMARY_GENERATED", timestamp=summary.created_at, video_id=str(video.id), video_name=video.filename, description=f"Summary generated for {video.filename}"))
        recent_moments = [moment for moment in video.key_moments if _in_date_range(moment.created_at, date_from, date_to)]
        if recent_moments:
            activity.append(RecentActivity(type="KEY_MOMENTS_DETECTED", timestamp=max(moment.created_at for moment in recent_moments), video_id=str(video.id), video_name=video.filename, description=f"{len(recent_moments)} key moments detected in {video.filename}"))
    activity.sort(key=lambda item: item.timestamp, reverse=True)

    transcript_insights = TranscriptInsights(total_transcripts=total_transcripts, total_words=total_transcript_words, average_words_per_transcript=round(total_transcript_words / total_transcripts, 2) if total_transcripts else 0, longest_transcript_words=max(transcript_word_counts, default=0), shortest_transcript_words=min(transcript_word_counts, default=0), total_characters=transcript_characters, average_characters=round(transcript_characters / total_transcripts, 2) if total_transcripts else 0)
    keyword_insights = _keywords(transcript_texts)
    recent_videos = video_intelligence[:20]
    overall_score = round(sum(score_values) / len(score_values), 2) if score_values else 0
    component_averages = []
    for index, template in enumerate(score_components[0] if score_components else []):
        component_averages.append(ScoreComponent(
            label=template.label,
            score=round(sum(components[index].score for components in score_components) / len(score_components), 2) if score_components else 0,
            weight=template.weight,
        ))
    intelligence_score = IntelligenceScore(
        score=overall_score,
        explanation=_score_explanation(overall_score, video_count, total_transcripts, completed_summaries, total_key_moments),
        components=component_averages,
    )
    ai_insights: list[AIInsight] = []
    if top_topics:
        ai_insights.append(AIInsight(category="TOPIC", title="Leading content topic", message=f"{top_topics[0].topic.title()} is the most frequently discussed topic in the selected content.", metric=f"{top_topics[0].percentage}% of keyword occurrences"))
    missing_summaries = max(total_transcripts - completed_summaries, 0)
    if missing_summaries:
        ai_insights.append(AIInsight(category="COVERAGE", title="Summaries need attention", message=f"{missing_summaries} transcript{'' if missing_summaries == 1 else 's'} do not have a completed summary yet.", metric=f"{missing_summaries} pending"))
        ai_insights.append(AIInsight(category="RECOMMENDATION", title="Complete the AI pipeline", message="Generate summaries for videos that already have transcript content to improve coverage."))
    if processing_videos:
        ai_insights.append(AIInsight(category="ATTENTION", title="Processing is still active", message=f"{processing_videos} video{'' if processing_videos == 1 else 's'} are still moving through the processing pipeline.", metric=f"{processing_videos} active"))
    if top_topics and top_topics[0].key_moment_count:
        ai_insights.append(AIInsight(category="KEY MOMENTS", title="Topic with the most signals", message=f"{top_topics[0].topic.title()} has the strongest overlap with detected key moments.", metric=f"{top_topics[0].key_moment_count} moments"))
    if total_transcripts and transcript_word_counts:
        longest_index = transcript_word_counts.index(max(transcript_word_counts))
        ai_insights.append(AIInsight(category="RICHNESS", title="Richest transcript", message="The longest transcript contains the broadest available content signal in this range.", metric=f"{transcript_word_counts[longest_index]:,} words"))
    ai_insights = ai_insights[:5]
    content_insights = ContentInsights(total_transcripts=total_transcripts, total_transcript_characters=transcript_characters, average_transcript_characters=round(transcript_characters / total_transcripts, 2) if total_transcripts else 0, total_summary_characters=summary_characters, top_keywords=keyword_insights, total_transcript_words=total_transcript_words, average_words_per_video=round(total_transcript_words / video_count, 2) if video_count else 0, key_moment_density=round(total_key_moments / total_transcript_words, 4) if total_transcript_words else 0)
    summary_insights = SummaryReports(total_summaries=total_summaries, completed_summaries=completed_summaries, videos_with_summaries=videos_with_summaries, generation_rate_percentage=round(completed_summaries / total_transcripts * 100, 2) if total_transcripts else 0, total_summary_characters=summary_characters, recent_activity=[RecentSummary(id=str(summary.id), video_id=str(summary.video_id), filename=filename, status=_value(summary.status), created_at=summary.created_at) for summary, filename in recent_summary_rows], total_summary_words=sum(summary_word_counts), average_summary_words=round(sum(summary_word_counts) / total_summaries, 2) if total_summaries else 0, longest_summary_words=max(summary_word_counts, default=0), shortest_summary_words=min(summary_word_counts, default=0))
    key_moment_insights = KeyMomentAnalytics(total_key_moments=total_key_moments, videos_with_key_moments=videos_with_key_moments, average_per_video=round(total_key_moments / video_count, 2) if video_count else 0, total_duration_seconds=round(moment_duration, 2), average_duration_seconds=round(moment_duration / total_key_moments, 2) if total_key_moments else 0, recent_activity=[RecentKeyMoment(id=str(moment.id), video_id=str(moment.video_id), filename=filename, title=moment.title, topic=moment.topic, importance_score=moment.importance_score, start_time=moment.start_time, end_time=moment.end_time) for moment, filename in recent_moment_rows], average_importance=round(sum(importance_scores) / total_key_moments, 2) if total_key_moments else 0, highest_importance=max(importance_scores, default=0), by_video=grouped_moments)
    video_activity = _fill_activity(upload_rows, date_from, date_to)
    processing_activity = _fill_activity(processing_rows, date_from, date_to)
    video_analytics = VideoAnalytics(upload_activity=video_activity, processing_activity=processing_activity, status_distribution=_count_items(status_rows), recent_videos=recent_videos)
    overview = OverviewAnalytics(total_videos=int(video_count), completed_videos=completed_videos, processing_videos=processing_videos, failed_videos=failed_videos, uploaded_videos=uploaded_videos, total_duration_seconds=int(total_duration), average_duration_seconds=round(float(average_duration), 2), total_summaries=total_summaries, total_transcripts=total_transcripts, total_key_moments=total_key_moments, total_users=int(total_users))

    return AnalyticsDashboard(overview=overview, video_analytics=video_analytics, summary_reports=summary_insights, content_insights=content_insights, key_moment_analytics=key_moment_insights, usage=UsageAnalytics(total_users=int(total_users), users_by_role=_count_items(role_rows), upload_activity=video_activity, processing_activity=processing_activity), processing_insights=ProcessingInsights(videos=_pipeline_stage(video_count, video_count), transcripts=_pipeline_stage(total_transcripts, video_count), summaries=_pipeline_stage(completed_summaries, total_transcripts), key_moments=_pipeline_stage(videos_with_key_moments, completed_videos)), transcript_insights=transcript_insights, keyword_insights=keyword_insights, content_insights_v2=content_insights, summary_insights=summary_insights, key_moment_insights=key_moment_insights, recent_activity=activity[:20], recent_videos=recent_videos, intelligence_score=intelligence_score, ai_insights=ai_insights, top_topics=top_topics, keyword_intelligence=keyword_intelligence, content_activity=content_activity, compression_insights={"average_transcript_words": round(average_transcript_words, 2), "average_summary_words": round(average_summary_words, 2), "compression_ratio": round(average_summary_words / average_transcript_words, 4) if average_transcript_words else 0}, importance_distribution=importance_distribution)
