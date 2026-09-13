"""Response schemas for the administrator analytics dashboard."""

from datetime import datetime

from pydantic import BaseModel


class CountItem(BaseModel):
    label: str
    count: int


class ActivityItem(BaseModel):
    date: str
    count: int


class ContentActivityItem(BaseModel):
    date: str
    transcripts: int
    summaries: int
    key_moments: int


class CompressionInsights(BaseModel):
    average_transcript_words: float
    average_summary_words: float
    compression_ratio: float


class ImportanceDistributionItem(BaseModel):
    label: str
    count: int
    average_importance: float


class RecentActivity(BaseModel):
    type: str
    timestamp: datetime
    video_id: str
    video_name: str
    description: str


class PipelineStage(BaseModel):
    count: int
    coverage_percentage: float


class ProcessingInsights(BaseModel):
    videos: PipelineStage
    transcripts: PipelineStage
    summaries: PipelineStage
    key_moments: PipelineStage


class RecentVideo(BaseModel):
    id: str
    filename: str
    owner_name: str
    status: str
    uploaded_at: datetime
    duration_seconds: int | None = None
    transcript_status: str | None = None
    summary_status: str | None = None
    key_moment_count: int = 0
    transcript_word_count: int = 0
    transcript_character_count: int = 0
    summary_word_count: int = 0
    topic_count: int = 0
    top_topics: list[str] = []
    top_keywords: list[str] = []
    ai_score: float = 0
    ai_score_components: dict[str, float] = {}
    average_importance: float = 0
    highest_importance: float = 0
    main_points_count: int = 0
    key_takeaways_count: int = 0


class OverviewAnalytics(BaseModel):
    total_videos: int
    completed_videos: int
    processing_videos: int
    failed_videos: int
    uploaded_videos: int
    total_duration_seconds: int
    average_duration_seconds: float
    total_summaries: int
    total_transcripts: int
    total_key_moments: int
    total_users: int


class VideoAnalytics(BaseModel):
    upload_activity: list[ActivityItem]
    processing_activity: list[ActivityItem]
    status_distribution: list[CountItem]
    recent_videos: list[RecentVideo]


class RecentSummary(BaseModel):
    id: str
    video_id: str
    filename: str
    status: str
    created_at: datetime


class SummaryReports(BaseModel):
    total_summaries: int
    completed_summaries: int
    videos_with_summaries: int
    generation_rate_percentage: float
    total_summary_characters: int
    recent_activity: list[RecentSummary]
    total_summary_words: int
    average_summary_words: float
    longest_summary_words: int
    shortest_summary_words: int


class KeywordItem(BaseModel):
    keyword: str
    count: int
    frequency: int
    rank: int


class ContentInsights(BaseModel):
    total_transcripts: int
    total_transcript_characters: int
    average_transcript_characters: float
    total_summary_characters: int
    top_keywords: list[KeywordItem]
    total_transcript_words: int
    average_words_per_video: float
    key_moment_density: float


class TranscriptInsights(BaseModel):
    total_transcripts: int
    total_words: int
    average_words_per_transcript: float
    longest_transcript_words: int
    shortest_transcript_words: int
    total_characters: int
    average_characters: float


class RecentKeyMoment(BaseModel):
    id: str
    video_id: str
    filename: str
    title: str
    topic: str | None
    importance_score: float
    start_time: float
    end_time: float


class KeyMomentAnalytics(BaseModel):
    total_key_moments: int
    videos_with_key_moments: int
    average_per_video: float
    total_duration_seconds: float
    average_duration_seconds: float
    recent_activity: list[RecentKeyMoment]
    average_importance: float
    highest_importance: float
    by_video: list[CountItem]


class UsageAnalytics(BaseModel):
    total_users: int
    users_by_role: list[CountItem]
    upload_activity: list[ActivityItem]
    processing_activity: list[ActivityItem]


class ScoreComponent(BaseModel):
    label: str
    score: float
    weight: float


class IntelligenceScore(BaseModel):
    score: float
    explanation: str
    components: list[ScoreComponent]


class AIInsight(BaseModel):
    category: str
    title: str
    message: str
    metric: str | None = None


class TopicInsight(BaseModel):
    topic: str
    percentage: float
    frequency: int
    video_count: int
    related_keywords: list[str] = []
    key_moment_count: int = 0
    summary_count: int = 0


class KeywordIntelligence(BaseModel):
    keyword: str
    frequency: int
    share_percentage: float
    video_count: int


class AnalyticsDashboard(BaseModel):
    overview: OverviewAnalytics
    video_analytics: VideoAnalytics
    summary_reports: SummaryReports
    content_insights: ContentInsights
    key_moment_analytics: KeyMomentAnalytics
    usage: UsageAnalytics
    processing_insights: ProcessingInsights
    transcript_insights: TranscriptInsights
    keyword_insights: list[KeywordItem]
    content_insights_v2: ContentInsights
    summary_insights: SummaryReports
    key_moment_insights: KeyMomentAnalytics
    recent_activity: list[RecentActivity]
    recent_videos: list[RecentVideo]
    intelligence_score: IntelligenceScore
    ai_insights: list[AIInsight]
    top_topics: list[TopicInsight]
    keyword_intelligence: list[KeywordIntelligence]
    content_activity: list[ContentActivityItem]
    compression_insights: CompressionInsights
    importance_distribution: list[ImportanceDistributionItem]