import type { CurrentUser, LoginResponse } from "../types/auth";

export interface VideoUploadResponse {
  id: number;
  filename: string;
  status: string;
  uploaded_at: string;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string | null;
}

export interface Transcript {
  id: number;
  video_id: number;
  text: string | null;
  segments: TranscriptSegment[] | null;
  language: string | null;
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
  created_at: string;
  updated_at: string;
}

export type SummaryStatus = "NOT_STARTED" | "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";

export interface Summary {
  id: number;
  transcript_id: number;
  short_summary: string | null;
  detailed_summary: string | null;
  status: SummaryStatus;
  created_at: string;
  updated_at: string;
}

export interface KeyMoment {
  id: number;
  start_time: number;
  end_time: number;
  title: string;
  topic: string | null;
  importance_score: number;
  text: string;
  highlight_path: string | null;
}

export interface KeyMomentsResponse {
  video_id: number;
  status: string;
  key_moments: KeyMoment[];
}

export interface RegistrationPayload {
  full_name: string;
  email: string;
  password: string;
  confirm_password: string;
  role: string;
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

const API_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
export const AUTH_EXPIRED_EVENT = "clipmind:auth-expired";

function notifyAuthenticationExpired(token: string | null) {
  if (typeof window !== "undefined" && token) {
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail: { token } }));
  }
}

export function getVideoMediaUrl(videoId: string | number, userId: string | number, filename: string) {
  void filename;
  return `${API_URL}/videos/media/videos/${userId}/${videoId}`;
}

export async function getVideoMediaObjectUrl(token: string, videoId: string | number, userId: string | number, filename: string) {
  const response = await fetch(getVideoMediaUrl(videoId, userId, filename), {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    if (response.status === 401) notifyAuthenticationExpired(token);
    throw new ApiError(response.status, await responseError(response, `Video request failed (${response.status})`));
  }
  return URL.createObjectURL(await response.blob());
}

async function responseError(response: Response, fallback: string) {
  const body = await response.text();
  if (!body) return fallback;
  try {
    const parsed = JSON.parse(body) as { detail?: string | { msg?: string }[] };
    if (Array.isArray(parsed.detail)) return parsed.detail.map(item => item.msg ?? "Invalid value").join("; ");
    if (parsed.detail) return parsed.detail;
  } catch {
    return body.slice(0, 500);
  }
  return fallback;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers });
  } catch (reason) {
    const detail = reason instanceof Error ? reason.message : "The request could not be sent.";
    throw new ApiError(0, `Cannot reach the backend at ${API_URL}. ${detail}`);
  }
  if (!response.ok) {
    if (response.status === 401) notifyAuthenticationExpired(headers.get("Authorization")?.replace(/^Bearer\s+/i, "") ?? null);
    throw new ApiError(response.status, await responseError(response, `Request failed (${response.status})`));
  }
  return response.json() as Promise<T>;
}

export function login(email: string, password: string) {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function register(payload: RegistrationPayload) {
  return request<{ id: string; email: string; role: string }>("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      name: payload.full_name,
      email: payload.email,
      role: payload.role,
      password: payload.password,
    }),
  });
}

export function getCurrentUser(token: string) {
  return request<CurrentUser>("/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function checkPermission(path: string, token: string) {
  return request<{ message: string }>(path, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function uploadVideo(token: string, file: File) {
  const body = new FormData();
  body.append("file", file);
  return request<VideoUploadResponse>("/videos/upload", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body,
  });
}

export function getUploadHistory(token: string, administrator = false) {
  return request<VideoUploadResponse[]>(administrator ? "/admin/upload-history" : "/videos/history", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getVideoStatuses(token: string) {
  return request<VideoUploadResponse[]>("/videos/status", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getVideos(token: string) {
  return request<VideoUploadResponse[]>("/videos/", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getTranscript(token: string, videoId: string | number) {
  return request<Transcript>(`/videos/${videoId}/transcript`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function generateTranscript(token: string, videoId: string | number) {
  return request<Transcript>(`/videos/${videoId}/transcript`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function updateTranscript(token: string, videoId: string | number, text: string) {
  return request<Transcript>(`/videos/${videoId}/transcript`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ text }),
  });
}

export function getSummary(token: string, videoId: string | number) {
  return request<Summary>(`/videos/${videoId}/summary`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function generateSummary(token: string, videoId: string | number, regenerate = false) {
  const path = regenerate ? `/videos/${videoId}/summary/regenerate` : `/videos/${videoId}/summary`;
  return request<Summary>(path, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getKeyMoments(token: string, videoId: string | number) {
  return request<KeyMomentsResponse>(`/videos/${videoId}/key-moments`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function generateKeyMoments(token: string, videoId: string | number) {
  return request<KeyMomentsResponse>(`/videos/${videoId}/key-moments/generate`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function downloadTranscript(token: string, videoId: string | number) {
  const response = await fetch(`${API_URL}/videos/${videoId}/transcript/download`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    if (response.status === 401) notifyAuthenticationExpired(token);
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? "Transcript download failed");
  }
  return response.blob();
}

export type AnalyticsRangeKey = "7d" | "30d" | "90d" | "all";

export interface AnalyticsRange {
  from?: string;
  to?: string;
}

export interface AnalyticsCountItem {
  label: string;
  count: number;
}

export interface AnalyticsActivity {
  date: string;
  count: number;
}

export interface AnalyticsContentActivity {
  date: string;
  transcripts: number;
  summaries: number;
  key_moments: number;
}

export interface AnalyticsRecentVideo {
  id: string;
  filename: string;
  owner_name: string;
  status: string;
  uploaded_at: string;
  duration_seconds: number | null;
  transcript_status: string | null;
  summary_status: string | null;
  key_moment_count: number;
  transcript_word_count: number;
  transcript_character_count: number;
  summary_word_count: number;
  topic_count: number;
  top_topics: string[];
  top_keywords: string[];
  ai_score: number;
  ai_score_components: Record<string, number>;
  average_importance: number;
  highest_importance: number;
  main_points_count: number;
  key_takeaways_count: number;
}

export interface AnalyticsRecentActivity {
  type: string;
  timestamp: string;
  video_id: string;
  video_name: string;
  description: string;
}

export interface AnalyticsKeyword {
  keyword: string;
  count: number;
  frequency: number;
  rank: number;
}

export interface AnalyticsTopic {
  topic: string;
  percentage: number;
  frequency: number;
  video_count: number;
  related_keywords: string[];
  key_moment_count: number;
  summary_count: number;
}

export interface AnalyticsInsight {
  category: string;
  title: string;
  message: string;
  metric: string | null;
}

export interface AnalyticsDashboard {
  overview: {
    total_videos: number;
    completed_videos: number;
    processing_videos: number;
    failed_videos: number;
    uploaded_videos: number;
    total_duration_seconds: number;
    average_duration_seconds: number;
    total_summaries: number;
    total_transcripts: number;
    total_key_moments: number;
    total_users: number;
  };
  video_analytics: {
    upload_activity: AnalyticsActivity[];
    processing_activity: AnalyticsActivity[];
    status_distribution: AnalyticsCountItem[];
    recent_videos: AnalyticsRecentVideo[];
  };
  summary_reports: {
    total_summaries: number;
    completed_summaries: number;
    videos_with_summaries: number;
    generation_rate_percentage: number;
    total_summary_characters: number;
    recent_activity: { id: string; video_id: string; filename: string; status: string; created_at: string }[];
    total_summary_words: number;
    average_summary_words: number;
    longest_summary_words: number;
    shortest_summary_words: number;
  };
  content_insights: {
    total_transcripts: number;
    total_transcript_characters: number;
    average_transcript_characters: number;
    total_summary_characters: number;
    top_keywords: AnalyticsKeyword[];
    total_transcript_words: number;
    average_words_per_video: number;
    key_moment_density: number;
  };
  key_moment_analytics: {
    total_key_moments: number;
    videos_with_key_moments: number;
    average_per_video: number;
    total_duration_seconds: number;
    average_duration_seconds: number;
    recent_activity: { id: string; video_id: string; filename: string; title: string; topic: string | null; importance_score: number; start_time: number; end_time: number }[];
    average_importance: number;
    highest_importance: number;
    by_video: AnalyticsCountItem[];
  };
  usage: {
    total_users: number;
    users_by_role: AnalyticsCountItem[];
    upload_activity: AnalyticsActivity[];
    processing_activity: AnalyticsActivity[];
  };
  processing_insights: {
    videos: { count: number; coverage_percentage: number };
    transcripts: { count: number; coverage_percentage: number };
    summaries: { count: number; coverage_percentage: number };
    key_moments: { count: number; coverage_percentage: number };
  };
  transcript_insights: {
    total_transcripts: number;
    total_words: number;
    average_words_per_transcript: number;
    longest_transcript_words: number;
    shortest_transcript_words: number;
    total_characters: number;
    average_characters: number;
  };
  keyword_insights: AnalyticsKeyword[];
  content_insights_v2: {
    total_transcripts: number;
    total_transcript_characters: number;
    average_transcript_characters: number;
    total_summary_characters: number;
    top_keywords: AnalyticsKeyword[];
    total_transcript_words: number;
    average_words_per_video: number;
    key_moment_density: number;
  };
  summary_insights: {
    total_summaries: number;
    completed_summaries: number;
    videos_with_summaries: number;
    generation_rate_percentage: number;
    total_summary_characters: number;
    recent_activity: { id: string; video_id: string; filename: string; status: string; created_at: string }[];
    total_summary_words: number;
    average_summary_words: number;
    longest_summary_words: number;
    shortest_summary_words: number;
  };
  key_moment_insights: {
    total_key_moments: number;
    videos_with_key_moments: number;
    average_per_video: number;
    total_duration_seconds: number;
    average_duration_seconds: number;
    recent_activity: { id: string; video_id: string; filename: string; title: string; topic: string | null; importance_score: number; start_time: number; end_time: number }[];
    average_importance: number;
    highest_importance: number;
    by_video: AnalyticsCountItem[];
  };
  recent_activity: AnalyticsRecentActivity[];
  recent_videos: AnalyticsRecentVideo[];
  intelligence_score: {
    score: number;
    explanation: string;
    components: { label: string; score: number; weight: number }[];
  };
  ai_insights: AnalyticsInsight[];
  top_topics: AnalyticsTopic[];
  keyword_intelligence: { keyword: string; frequency: number; share_percentage: number; video_count: number }[];
  content_activity: AnalyticsContentActivity[];
  compression_insights: {
    average_transcript_words: number;
    average_summary_words: number;
    compression_ratio: number;
  };
  importance_distribution: { label: string; count: number; average_importance: number }[];
}

function analyticsPath(path: string, range?: AnalyticsRange) {
  const params = new URLSearchParams();
  if (range?.from) params.set("from", range.from);
  if (range?.to) params.set("to", range.to);
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export function getAdminAnalytics(token: string, range?: AnalyticsRange) {
  return request<AnalyticsDashboard>(analyticsPath("/admin/analytics", range), {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getCreatorAnalytics(token: string, range?: AnalyticsRange) {
  return request<AnalyticsDashboard>(analyticsPath("/analytics", range), {
    headers: { Authorization: `Bearer ${token}` },
  });
}
