"""Gemini interpretation of verified analytics service output."""

import json
from typing import Any

from google import genai
from google.genai import types

from app.config import settings
from app.schemas.analytics import AnalyticsAIInsights, AnalyticsDashboard
from app.services.gemini import (
    GEMINI_SHORT_REQUEST_TIMEOUT_SECONDS,
    generate_content_with_retry,
    gemini_http_options,
)


def _gemini_response_schema(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {
            key: _gemini_response_schema(value)
            for key, value in schema.items()
            if key not in {"additionalProperties", "additional_properties"}
        }
    if isinstance(schema, list):
        return [_gemini_response_schema(value) for value in schema]
    return schema


def build_ai_analytics_snapshot(analytics: AnalyticsDashboard) -> dict:
    """Select non-personal, database-derived metrics for Gemini interpretation."""
    overview = analytics.overview
    summaries = analytics.summary_insights
    topics = analytics.top_topics[:10]
    keywords = analytics.keyword_intelligence[:10]

    return {
        "total_videos": overview.total_videos,
        "videos_analyzed": analytics.processing_insights.videos.count,
        "completed_videos": overview.completed_videos,
        "processing_videos": overview.processing_videos,
        "pending_videos": overview.uploaded_videos,
        "failed_videos": overview.failed_videos,
        "file_uploads": overview.uploaded_video_count,
        "youtube_uploads": overview.youtube_video_count,
        "total_duration_seconds": overview.total_duration_seconds,
        "average_duration_seconds": overview.average_duration_seconds,
        "video_status_distribution": [item.model_dump() for item in analytics.video_analytics.status_distribution],
        "transcripts": analytics.transcript_insights.total_transcripts,
        "transcript_words": analytics.transcript_insights.total_words,
        "longest_transcript_words": analytics.transcript_insights.longest_transcript_words,
        "summaries": summaries.total_summaries,
        "completed_summaries": summaries.completed_summaries,
        "summary_coverage_percentage": summaries.generation_rate_percentage,
        "key_moments": analytics.key_moment_insights.total_key_moments,
        "key_moment_importance_distribution": [item.model_dump() for item in analytics.importance_distribution],
        "top_topics": [
            {
                "topic": item.topic,
                "frequency": item.frequency,
                "share_percentage": item.percentage,
                "video_count": item.video_count,
            }
            for item in topics
        ],
        "top_keywords": [
            {
                "keyword": item.keyword,
                "frequency": item.frequency,
                "share_percentage": item.share_percentage,
                "video_count": item.video_count,
            }
            for item in keywords
        ],
        "user_count": overview.total_users,
        "upload_activity": [item.model_dump() for item in analytics.video_analytics.upload_activity],
        "processing_activity": [item.model_dump() for item in analytics.video_analytics.processing_activity],
    }


def generate_analytics_ai_insights(snapshot: dict) -> AnalyticsAIInsights:
    """Ask the configured Gemini model to interpret, but never recalculate, metrics."""
    api_key = (settings.gemini_api_key or "").strip()
    if not api_key:
        raise ValueError("Gemini API key is not configured.")

    client = genai.Client(
        api_key=api_key,
        http_options=gemini_http_options(GEMINI_SHORT_REQUEST_TIMEOUT_SECONDS),
    )
    model_name = (settings.gemini_model or "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    prompt = f"""You are the AI analytics interpretation layer for ClipMind AI.

The application has already calculated the supplied analytics directly from its database. Treat every supplied numerical metric as authoritative. Do not change, recalculate, estimate, invent, or contradict numerical values. In every narrative or prose field, do not use digits, number words from zero through twelve, ordinal words such as first, second, or third, or any numerical quantities, counts, percentages, dates, durations, IDs, or other numeric-looking values. Express insights qualitatively instead, using wording such as "the leading topic", "another important area", "a major pattern", "the most prominent theme", "a smaller portion", or "recent activity"; exact figures remain visible beside your interpretation. Do not invent users, videos, topics, keywords, processing events, trends, or content. Only make conclusions supported by the supplied data. If the supplied data is insufficient to determine something, explicitly state that there is insufficient data.

Interpret the verified data in simple, useful language. Cover video processing, upload sources, video duration and activity; summary coverage and completion; supplied topics, transcript richness and key-moment distribution; usage and activity over the selected period; and the supplied keyword frequencies. Identify only supported attention areas. If there is no meaningful issue, keep attention neutral or empty. Recommendations must be practical and based only on these analytics. Do not invent a summary-quality score.

Return only JSON matching the requested schema. Do not add fields or markdown.

VERIFIED ANALYTICS SNAPSHOT:
{json.dumps(snapshot, ensure_ascii=True, separators=(",", ":"))}"""
    response = generate_content_with_retry(
        lambda: client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=1600,
                response_mime_type="application/json",
                response_schema=_gemini_response_schema(AnalyticsAIInsights.model_json_schema()),
            ),
        ),
        operation="analytics_ai_insights",
        model=model_name,
        request_timeout_seconds=GEMINI_SHORT_REQUEST_TIMEOUT_SECONDS,
    )
    if not getattr(response, "text", None):
        raise ValueError("Gemini returned no text content.")
    return AnalyticsAIInsights.model_validate_json(response.text)