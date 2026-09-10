import type { CurrentUser, LoginResponse } from "../types/auth";

export interface VideoUploadResponse {
  id: string;
  filename: string;
  mime_type: string;
  file_size_bytes: number;
  processing_status: string;
  uploaded_at: string;
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
}

export interface VideoStatus {
  id: string;
  processing_status: string;
}

export interface VideoListItem {
  id: string;
  filename: string;
  mime_type: string;
  file_size_bytes: number;
  duration_seconds: number | null;
  processing_status: string;
  uploaded_at: string;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

export interface Transcript {
  id: number;
  video_id: string;
  text: string;
  segments: TranscriptSegment[];
  language: string | null;
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
  created_at: string;
  updated_at: string | null;
}

export interface Summary {
  id: number;
  transcript_id: number;
  short_summary: string | null;
  detailed_summary: string | null;
  status: "NOT_STARTED" | "PROCESSING" | "COMPLETED" | "FAILED";
  created_at: string;
  updated_at: string | null;
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

async function responseError(response: Response, fallback: string) {
  if (response.status === 401 || response.status === 403) return "Your session has expired. Please sign in again.";
  if (response.status === 404) return "Transcript information is not available for this video yet.";
  if (response.status === 422) return "Invalid request. Please try again.";
  if (response.status >= 500) return "The backend encountered an error. Please try again.";
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
    throw new ApiError(0, `Cannot reach the backend at ${API_URL}.`);
  }
  if (!response.ok) {
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
  return request<VideoUploadResponse[]>("/videos/history", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getVideoStatuses(token: string) {
  return request<VideoStatus[]>("/videos/status", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getVideos(token: string) {
  return request<VideoListItem[]>("/videos/", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getTranscript(token: string, videoId: string) {
  return request<Transcript>(`/videos/${videoId}/transcript`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getSummary(token: string, videoId: string) {
  return request<Summary>(`/videos/${videoId}/summary`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function generateSummary(token: string, videoId: string) {
  return request<Summary>(`/videos/${videoId}/summary`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getKeyMoments(token: string, videoId: string) {
  return request<{ video_id: string; status: string; key_moments: KeyMoment[] }>(`/videos/${videoId}/key-moments`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(result => result.key_moments);
}

export function retrySummary(token: string, videoId: string) {
  return request<Summary>(`/videos/${videoId}/summary/retry`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}
