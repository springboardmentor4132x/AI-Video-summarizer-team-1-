import type { CurrentUser, LoginResponse, Role } from "../types/auth";
import { API_BASE_URL, withApiBase } from "../config";

export interface VideoUploadResponse {
  id: string;
  filename: string;
  mime_type: string;
  file_size_bytes: number;
  processing_status: string;
  source_type?: "UPLOAD" | "YOUTUBE";
  source_url?: string | null;
  uploaded_at: string;
}

export interface YouTubeVideoResponse {
  video_id: string;
  source_type: "YOUTUBE";
  source_url: string;
  status: string;
}

export interface UploadHistoryEvent {
  id: string;
  video_id: string;
  filename: string;
  owner_id: string;
  owner_name: string;
  status: string;
  timestamp: string;
  notes: string | null;
  mime_type: string;
  file_size_bytes: number;
  duration_seconds: number | null;
  source_type: "UPLOAD" | "YOUTUBE";
}

export interface VideoStatus {
  id: string;
  filename: string;
  processing_status: string;
  updated_at: string;
  latest_note: string | null;
}

export interface VideoListItem {
  id: string;
  filename: string;
  mime_type: string;
  file_size_bytes: number;
  duration_seconds: number | null;
  processing_status: string;
  source_type?: "UPLOAD" | "YOUTUBE";
  source_url?: string | null;
  uploaded_at: string;
  owner_id: string;
  owner_name: string;
  storage_key?: string | null;
}

export interface TranscriptSegment {
  start_time: number;
  end_time: number;
  text: string;
}

export interface Transcript {
  id: string;
  video_id: string;
  text: string;
  segments: TranscriptSegment[];
  language: string | null;
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface Summary {
  id: string;
  video_id: string;
  transcript_id?: string | number;
  content: string;
  overview: string;
  short_summary?: string | null;
  detailed_summary?: string | null;
  main_points: string[];
  key_takeaways: string[];
  duration_seconds: number | null;
  status: "NOT_STARTED" | "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface KeyMoment {
  id: string;
  video_id: string;
  start_time: number;
  end_time: number;
  title: string;
  topic: string | null;
  description?: string;
  text: string;
  importance_score: number;
  transcript_text: string;
  created_at: string;
}

export interface McqQuestion {
  question: string;
  options: string[];
  correct_answer: string;
  explanation: string;
  difficulty: "Easy" | "Medium" | "Hard";
  topic: string;
  source: "Transcript" | "Summary" | "Key Moment";
  timestamp: number | string | null;
}

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
  processing_insights: Record<"videos" | "transcripts" | "summaries" | "key_moments", { count: number; coverage_percentage: number }>;
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
  content_insights_v2: AnalyticsDashboard["content_insights"];
  summary_insights: AnalyticsDashboard["summary_reports"];
  key_moment_insights: AnalyticsDashboard["key_moment_analytics"];
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
  compression_insights: { average_transcript_words: number; average_summary_words: number; compression_ratio: number };
  importance_distribution: { label: string; count: number; average_importance: number }[];
}

export type AdminAnalytics = AnalyticsDashboard;

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

const API_URL = API_BASE_URL;
const INVALID_TOKEN_VALUES = new Set(["", "undefined", "null"]);
export const AUTH_EXPIRED_EVENT = "clipmind:auth-expired";

export function getVideoMediaUrl(videoId: string, userId: string, filename: string, storageKey?: string | null) {
  if (storageKey && storageKey.trim()) {
    return `${API_URL}/media/${encodeURI(storageKey.trim())}`;
  }

  const extension = filename.includes(".") ? filename.slice(filename.lastIndexOf(".")) : "";
  const safeFilename = filename.trim() || `${videoId}${extension || ".mp4"}`;
  const suffix = safeFilename.includes(".") ? safeFilename.slice(safeFilename.lastIndexOf(".")) : extension || ".mp4";
  return `${API_URL}/media/videos/${userId}/${videoId}${suffix}`;
}

export async function getVideoMediaBlobUrl(token: string, videoId: string, userId?: string | number) {
  ensureValidAuthorization(token);
  const response = await fetch(`${API_URL}/videos/media/videos/${userId ?? ""}/${videoId}`, {
    headers: getAuthHeaders(token),
  });
  if (!response.ok) {
    const message = await responseError(response, "Video playback could not be loaded.");
    throw new ApiError(response.status, message);
  }
  return URL.createObjectURL(await response.blob());
}

export function getVideoMediaObjectUrl(token: string, videoId: string | number, userId: string | number, _filename: string) {
  return getVideoMediaBlobUrl(token, String(videoId), userId);
}

export function getAuthHeaders(token?: string | null): Record<string, string> {
  const candidate = token?.trim();
  if (!candidate || INVALID_TOKEN_VALUES.has(candidate.toLowerCase())) {
    return {};
  }
  return { Authorization: `Bearer ${candidate}` };
}

function ensureValidAuthorization(token?: string | null) {
  const candidate = token?.trim();
  if (!candidate || INVALID_TOKEN_VALUES.has(candidate.toLowerCase())) {
    throw new ApiError(401, "Your session has expired. Please log in again.");
  }
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
  const authHeader = headers.get("Authorization");
  if (authHeader) {
    const candidate = authHeader.replace(/^Bearer\s+/i, "").trim();
    if (!candidate || INVALID_TOKEN_VALUES.has(candidate.toLowerCase())) {
      if (typeof window !== "undefined" && authHeader) window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail: { token: authHeader.replace(/^Bearer\\s+/i, "") } }));
      throw new ApiError(401, "Your session has expired. Please log in again.");
    }
  }
  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  const requestUrl = `${API_URL}${path}`;
  if (import.meta.env.DEV) {
    console.debug(`[ClipMind API] ${options.method ?? "GET"} ${requestUrl}`);
  }
  try {
    response = await fetch(requestUrl, { ...options, headers });
  } catch (reason) {
    if (import.meta.env.DEV) {
      const error = reason instanceof Error ? reason : new Error(String(reason));
      console.error(`[ClipMind API] network failure ${requestUrl}`, { name: error.name, message: error.message });
    }
    throw new ApiError(
      0,
      "Cannot connect to the ClipMind AI backend. Check that the frontend is opened from the configured local address and that the backend is reachable.",
    );
  }
  if (import.meta.env.DEV) {
    console.debug(`[ClipMind API] response ${response.status} ${requestUrl}`);
  }
  if (!response.ok) {
    const message = await responseError(response, `Request failed (${response.status})`);
    if (import.meta.env.DEV) {
      console.warn(`[ClipMind API] HTTP error ${response.status} ${requestUrl}`, { body: message });
    }
    if (response.status === 401) {
      if (path === "/auth/login") {
        throw new ApiError(401, "Invalid email or password.");
      }
      throw new ApiError(401, "Your session has expired. Please log in again.");
    }
    if (response.status === 403) {
      throw new ApiError(403, "Your account does not have permission to access this workspace.");
    }
    if (response.status >= 500) {
      throw new ApiError(response.status, message || "Server error. Please try again later.");
    }
    throw new ApiError(response.status, message || "Authentication service is temporarily unavailable.");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function login(email: string, password: string) {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function register(payload: RegistrationPayload) {
  return request<{ id: number; name: string; email: string; role: Role; created_at: string }>("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      name: payload.full_name.trim(),
      email: payload.email.trim(),
      password: payload.password,
      role: payload.role,
    }),
  });
}

export function getCurrentUser(token: string) {
  ensureValidAuthorization(token);
  return request<Omit<CurrentUser, "full_name"> & { full_name?: string }>("/auth/me", {
    headers: getAuthHeaders(token),
  }).then(user => ({ ...user, full_name: user.full_name ?? user.name }));
}

function analyticsPath(path: string, range?: AnalyticsRange) {
  const params = new URLSearchParams();
  if (range?.from) params.set("from", range.from);
  if (range?.to) params.set("to", range.to);
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export function getAdminAnalytics(token: string, range?: AnalyticsRange) {
  ensureValidAuthorization(token);
  return request<AnalyticsDashboard>(analyticsPath("/admin/analytics", range), {
    headers: getAuthHeaders(token),
  });
}

export function getCreatorAnalytics(token: string, range?: AnalyticsRange) {
  ensureValidAuthorization(token);
  return request<AnalyticsDashboard>(analyticsPath("/analytics", range), {
    headers: getAuthHeaders(token),
  });
}

export async function checkPermission(path: string, token: string) {
  ensureValidAuthorization(token);
  return request<{ message: string }>(path, {
    headers: getAuthHeaders(token),
  });
}

export function uploadVideo(token: string, file: File) {
  ensureValidAuthorization(token);
  const body = new FormData();
  body.append("file", file);
  return request<VideoUploadResponse>("/videos/upload", {
    method: "POST",
    headers: getAuthHeaders(token),
    body,
  });
}

export function processYouTubeVideo(token: string, youtubeUrl: string) {
  ensureValidAuthorization(token);
  return request<YouTubeVideoResponse>("/videos/youtube", {
    method: "POST",
    headers: getAuthHeaders(token),
    body: JSON.stringify({ youtube_url: youtubeUrl }),
  });
}

export function getUploadHistory(token: string, administrator = false) {
  ensureValidAuthorization(token);
  return request<UploadHistoryEvent[]>(administrator ? "/admin/upload-history" : "/videos/history", {
    headers: getAuthHeaders(token),
  });
}

export function getVideoStatuses(token: string, limit = 500) {
  ensureValidAuthorization(token);
  const params = new URLSearchParams({ limit: String(limit) });
  return request<VideoStatus[]>(`/videos/status?${params.toString()}`, {
    headers: getAuthHeaders(token),
  });
}

export function getVideos(token: string, limit = 500) {
  ensureValidAuthorization(token);
  const params = new URLSearchParams({ limit: String(limit) });
  return request<VideoListItem[]>(`/videos/?${params.toString()}`, {
    headers: getAuthHeaders(token),
  });
}

export function deleteVideo(token: string, videoId: string | number) {
  ensureValidAuthorization(token);
  return request<{ message: string; video_id: string }>(`/videos/${videoId}`, {
    method: "DELETE",
    headers: getAuthHeaders(token),
  });
}

export function getTranscript(token: string, videoId: string | number) {
  ensureValidAuthorization(token);
  return request<Transcript>(`/videos/${videoId}/transcript`, {
    headers: getAuthHeaders(token),
  });
}

export function generateTranscript(token: string, videoId: string | number) {
  ensureValidAuthorization(token);
  return request<Transcript>(`/videos/${videoId}/transcript`, {
    method: "POST",
    headers: getAuthHeaders(token),
  });
}

export function updateTranscript(token: string, videoId: string | number, text: string) {
  ensureValidAuthorization(token);
  return request<Transcript>(`/videos/${videoId}/transcript`, {
    method: "PATCH",
    headers: getAuthHeaders(token),
    body: JSON.stringify({ text }),
  });
}

export function getSummary(token: string, videoId: string | number) {
  ensureValidAuthorization(token);
  return request<Summary>(`/videos/${videoId}/summary`, {
    headers: getAuthHeaders(token),
  });
}

export function generateSummary(token: string, videoId: string | number, regenerate = false) {
  ensureValidAuthorization(token);
  const query = regenerate ? "?regenerate=true" : "";
  return request<Summary>(`/videos/${videoId}/summary${query}`, {
    method: "POST",
    headers: getAuthHeaders(token),
  });
}

export function retrySummary(token: string, videoId: string | number) {
  ensureValidAuthorization(token);
  return request<Summary>(`/videos/${videoId}/summary/retry`, {
    method: "POST",
    headers: getAuthHeaders(token),
  });
}

export function getKeyMoments(token: string, videoId: string | number) {
  ensureValidAuthorization(token);
  return request<{ video_id: number; status: string; key_moments: KeyMoment[] }>(`/videos/${videoId}/key-moments`, {
    headers: getAuthHeaders(token),
  });
}

export function getExpectedMcqs(token: string, videoId: string | number) {
  ensureValidAuthorization(token);
  return request<McqQuestion[]>(`/videos/${videoId}/mcqs`, {
    headers: getAuthHeaders(token),
  });
}

export function generateKeyMoments(token: string, videoId: string | number) {
  ensureValidAuthorization(token);
  return request<{ video_id: number; status: string; key_moments: KeyMoment[] }>(`/videos/${videoId}/key-moments/generate`, {
    method: "POST",
    headers: getAuthHeaders(token),
  });
}

export async function downloadTranscript(token: string, videoId: string | number) {
  ensureValidAuthorization(token);
  const response = await fetch(withApiBase(`/videos/${videoId}/transcript/download`), {
    headers: getAuthHeaders(token),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const message = body.detail ?? "Transcript download failed";
    if (response.status === 401 || response.status === 403) {
      throw new ApiError(response.status, "Your session has expired. Please log in again.");
    }
    throw new ApiError(response.status, message);
  }
  return response.blob();
}
