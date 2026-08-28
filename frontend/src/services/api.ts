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
  uploaded_at: string;
  owner_id: string;
  owner_name: string;
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
  content: string;
  created_at: string;
  updated_at: string;
}

export interface KeyMoment {
  id: string;
  video_id: string;
  start_time: number;
  end_time: number;
  title: string;
  description: string;
  importance_score: number;
  transcript_text: string;
  created_at: string;
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

export function getVideoMediaUrl(videoId: string, userId: string, filename: string) {
  const extension = filename.includes(".") ? filename.slice(filename.lastIndexOf(".")) : "";
  return `${API_URL}/media/videos/${userId}/${videoId}${extension}`;
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
    body: JSON.stringify(payload),
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
  return request<UploadHistoryEvent[]>(administrator ? "/admin/upload-history" : "/videos/history", {
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

export function generateTranscript(token: string, videoId: string) {
  return request<Transcript>(`/videos/${videoId}/transcript`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function updateTranscript(token: string, videoId: string, text: string) {
  return request<Transcript>(`/videos/${videoId}/transcript`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ text }),
  });
}

export function getSummary(token: string, videoId: string) {
  return request<Summary>(`/videos/${videoId}/summary`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function generateSummary(token: string, videoId: string, regenerate = false) {
  const query = regenerate ? "?regenerate=true" : "";
  return request<Summary>(`/videos/${videoId}/summary${query}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getKeyMoments(token: string, videoId: string) {
  return request<KeyMoment[]>(`/videos/${videoId}/key-moments`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function generateKeyMoments(token: string, videoId: string) {
  return request<KeyMoment[]>(`/videos/${videoId}/key-moments/generate`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function downloadTranscript(token: string, videoId: string) {
  const response = await fetch(`${API_URL}/videos/${videoId}/transcript/download`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? "Transcript download failed");
  }
  return response.blob();
}
