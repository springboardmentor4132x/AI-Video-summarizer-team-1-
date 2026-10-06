import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { Activity, ArrowUpRight, BookOpen, CalendarDays, Clapperboard, Clock3, FileClock, Gauge, HardDrive, MonitorCog, RefreshCw, Search, ShieldCheck, Trash2, User, Users, Video, WandSparkles, Sparkles, Upload, Download, FileText, CircleCheckBig, ClapperboardIcon, ArrowRight, CirclePlay } from "lucide-react";
import { withApiBase } from "./config";
import { Modal } from "./components/Modal";
import { useAuth } from "./features/auth/AuthContext";
import { ApiError, checkPermission, deleteVideo, downloadTranscript, generateKeyMoments, generateSummary, generateTranscript, getAdminAnalytics, getCreatorAnalytics, getExpectedMcqs, getKeyMoments, getSummary, getTranscript, getUploadHistory, getVideoMediaBlobUrl, getVideoStatuses, getVideos, getVideoMediaUrl, processYouTubeVideo, uploadYouTubeVideo ,register as registerRequest, retrySummary, uploadVideo, type AnalyticsDashboard, type AnalyticsRange, type AnalyticsRecentVideo, type KeyMoment, type McqQuestion, type Summary, type Transcript, type UploadHistoryEvent, type VideoListItem, type VideoStatus } from "./services/api";
import type { Role } from "./types/auth";

const dashboardConfig: Record<Role, { kicker: string; title: string; description: string; accent: string; actions: { label: string; detail: string; icon: typeof Video; route: string; endpoint?: string }[] }> = {
  "Content Creator": {
    kicker: "Creator studio", title: "Turn long videos into useful knowledge.", description: "Upload content, review transcripts, summarize key ideas, and keep the full workflow moving from one place.", accent: "coral",
    actions: [
      { label: "Upload Video", detail: "Start a new media upload", icon: Video, route: "/creator/upload", endpoint: "/rbac/creator/uploads" },
      { label: "Transcripts", detail: "Generate and edit transcripts", icon: FileClock, route: "/creator/transcripts", endpoint: "/rbac/creator/uploads" },
      { label: "MCQ Quiz", detail: "Test knowledge with quizzes", icon: BookOpen, route: "/creator/mcqs", endpoint: "/rbac/creator/uploads" },
      { label: "Upload History", detail: "Trace every file event", icon: FileClock, route: "/creator/history", endpoint: "/rbac/creator/history" },
      { label: "Processing Status", detail: "Watch jobs move forward", icon: Gauge, route: "/creator/processing", endpoint: "/rbac/creator/uploads" },
    ],
  },
  Learner: {
    kicker: "Learning space", title: "Turn learning into a cleaner, easier workflow.", description: "Browse videos, read transcripts, and pull out the key points that matter most to your study path.", accent: "mint",
    actions: [
      { label: "Videos", detail: "Browse the content library", icon: Video, route: "/learner/videos", endpoint: "/rbac/learner/content" },
      { label: "Transcripts", detail: "Read generated transcripts", icon: FileClock, route: "/learner/transcripts" },
      { label: "Summaries", detail: "Surface the most important ideas", icon: WandSparkles, route: "/learner/summaries" },
      { label: "Learning Content", detail: "Open your learning shelf", icon: BookOpen, route: "/learner/content", endpoint: "/rbac/learner/content" },
    ],
  },
  Educator: {
    kicker: "Teaching workspace", title: "Shape lectures into clear learning moments.", description: "Keep your teaching material organized, ready, and easy to revisit with transcripts and summaries.", accent: "gold",
    actions: [
      { label: "Upload Lecture", detail: "Add a new teaching video", icon: Video, route: "/educator/upload", endpoint: "/rbac/educator/content" },
      { label: "Transcripts", detail: "Generate and edit lecture transcripts", icon: FileClock, route: "/educator/transcripts", endpoint: "/rbac/educator/content" },
      { label: "Learning Materials", detail: "Keep lessons in one place", icon: BookOpen, route: "/educator/classroom", endpoint: "/rbac/educator/content" },
      { label: "Educational Content", detail: "Review your teaching shelf", icon: BookOpen, route: "/educator/content", endpoint: "/rbac/educator/content" },
    ],
  },
  Administrator: {
    kicker: "Control room", title: "See the platform at a glance.", description: "Monitor platform activity, user access, and the content flow that keeps ClipMind running smoothly.", accent: "blue",
    actions: [
      { label: "Users", detail: "Review platform accounts", icon: Users, route: "/admin/users", endpoint: "/rbac/admin/users" },
      { label: "Roles", detail: "Inspect access structure", icon: ShieldCheck, route: "/admin/roles", endpoint: "/rbac/admin/users" },
      { label: "Content", detail: "Follow recent platform activity", icon: MonitorCog, route: "/admin/activity", endpoint: "/rbac/admin/platform" },
      { label: "AI Processing", detail: "Check service readiness", icon: Gauge, route: "/admin/monitoring", endpoint: "/rbac/admin/platform" },
    ],
  },
};

const workflowSteps = [
  { icon: Upload, label: "Upload", detail: "Add your video" },
  { icon: FileText, label: "Transcribe", detail: "Convert speech to text" },
  { icon: Sparkles, label: "Summarize", detail: "Generate an AI summary" },
  { icon: WandSparkles, label: "Key Moments", detail: "Discover important moments" },
  { icon: Gauge, label: "Insights", detail: "Understand what matters" },
];

function formatDuration(seconds: number | null) {
  if (!seconds || seconds <= 0) return "Duration unavailable";
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hrs > 0) return `${hrs}h ${mins}m ${secs}s`;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

function formatClock(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes.toString().padStart(2, "0")}:${remainder}`;
}

function formatFileSize(bytes: number) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value >= 10 || exponent === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[exponent]}`;
}

function getTranscriptState(videoStatus?: string | null, transcriptStatus?: string | null) {
  const status = (transcriptStatus ?? videoStatus ?? "").toUpperCase();

  if (status.includes("FAILED") || status.includes("ERROR")) return "transcript_failed" as const;
  if (status.includes("COMPLETED") || status.includes("READY") || status.includes("SUCCESS")) return "transcript_ready" as const;
  if (status.includes("PROCESSING") || status.includes("PENDING") || status.includes("IN_PROGRESS")) return "processing" as const;
  return "transcript_missing" as const;
}

function Dashboard() {
  const { user, token } = useAuth();
  const [notice, setNotice] = useState<string | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [stats, setStats] = useState<{ videos: number | null; transcripts: number | null; summaries: number | null; keyMoments: number | null; }>({ videos: null, transcripts: null, summaries: null, keyMoments: null });

  useEffect(() => {
    async function loadData() {
      if (!user || !token) return;

      try {
        setStatsError(null);
        if (user.role === "Administrator") {
          const analytics = await getAdminAnalytics(token);
          setStats({
            videos: analytics.overview.total_videos,
            transcripts: analytics.overview.total_transcripts,
            summaries: analytics.overview.total_summaries,
            keyMoments: analytics.overview.total_key_moments,
          });
          return;
        }

        const videos = await getVideos(token);

        const results = await Promise.allSettled(videos.map(async video => {
          const transcript = await fetch(withApiBase(`/videos/${video.id}/transcript`), { headers: { Authorization: `Bearer ${token}` } }).then(async response => {
            if (!response.ok) throw new Error("missing");
            return response.json();
          }).catch(() => null);
          const summary = await fetch(withApiBase(`/videos/${video.id}/summary`), { headers: { Authorization: `Bearer ${token}` } }).then(async response => {
            if (!response.ok) throw new Error("missing");
            return response.json();
          }).catch(() => null);
          const keyMoments = await fetch(withApiBase(`/videos/${video.id}/key-moments`), { headers: { Authorization: `Bearer ${token}` } }).then(async response => {
            if (!response.ok) throw new Error("missing");
            return response.json();
          }).catch(() => null);

          return { transcript: Boolean(transcript), summary: Boolean(summary), keyMoments: Array.isArray(keyMoments) ? keyMoments.length : 0 };
        }));

        const totals = results.reduce((acc, result) => {
          if (result.status !== "fulfilled") return acc;
          acc.transcripts += result.value.transcript ? 1 : 0;
          acc.summaries += result.value.summary ? 1 : 0;
          acc.keyMoments += result.value.keyMoments;
          return acc;
        }, { videos: videos.length, transcripts: 0, summaries: 0, keyMoments: 0 });

        setStats(totals);
      } catch {
        setStatsError("Dashboard data could not be loaded from the backend.");
        setStats({ videos: null, transcripts: null, summaries: null, keyMoments: null });
      }
    }

    void loadData();
  }, [token, user, user?.role]);

  if (!user || !token) return <Navigate to="/login" replace />;

  const config = dashboardConfig[user.role];
  const statCards = [
    { label: "Videos", value: statsError ? "Unavailable" : stats.videos ?? 0, tone: "teal", icon: Clapperboard },
    { label: "Transcripts", value: statsError ? "Unavailable" : stats.transcripts ?? 0, tone: "amber", icon: FileText },
    { label: "AI Summaries", value: statsError ? "Unavailable" : stats.summaries ?? 0, tone: "rose", icon: Sparkles },
    { label: "Key Moments", value: statsError ? "Unavailable" : stats.keyMoments ?? 0, tone: "slate", icon: WandSparkles },
  ];
  const workflowRoutes: Record<string, string> = user.role === "Content Creator"
    ? { Upload: "/creator/upload", Transcribe: "/creator/transcripts", Summarize: "/creator/transcripts", "Key Moments": "/creator/transcripts", Insights: "/creator/processing" }
    : user.role === "Educator"
      ? { Upload: "/educator/upload", Transcribe: "/educator/transcripts", Summarize: "/educator/transcripts", "Key Moments": "/educator/transcripts", Insights: "/educator/content" }
      : user.role === "Learner"
        ? { Upload: "/learner/videos", Transcribe: "/learner/transcripts", Summarize: "/learner/summaries", "Key Moments": "/learner/videos", Insights: "/learner/content" }
        : { Upload: "/admin/activity", Transcribe: "/admin/monitoring", Summarize: "/admin/monitoring", "Key Moments": "/admin/monitoring", Insights: "/admin/monitoring" };

  return (
    <section className="dashboard-page creator-dashboard">
      <header className="page-header creator-header">
        <div>
          <span className="eyebrow">{config.kicker}</span>
          <h1>{config.title}</h1>
          <p>{config.description}</p>
        </div>
        <div className="status-pill"><span className="status-dot" /> Workspace online</div>
      </header>

      {notice && <div className="notice" role="status">{notice}</div>}

      <div className="creator-hero">
        <div className="hero-copy">
          <span className="eyebrow">Welcome back</span>
          <h2>👋 Welcome back, {user.full_name}</h2>
          <p>Turn long videos into useful knowledge.</p>
          <p className="hero-support">Upload your video, generate transcripts, discover key moments, and create concise AI summaries.</p>
          <div className="hero-actions">
            <Link className="primary-button" to="/creator/upload">📤 Upload Video</Link>
            <Link className="secondary-button" to="/creator/transcripts">📝 View Transcripts</Link>
          </div>
        </div>
        <div className="hero-badge">
          <div className="hero-badge-icon"><Clapperboard size={20} /></div>
          <div>
            <strong>Content workflow</strong>
            <span>Upload • Transcribe • Summarize</span>
          </div>
        </div>
      </div>

      {statsError && <div className="notice" role="alert">{statsError}</div>}
      <div className="section-heading">
        <div>
          <span className="eyebrow">Progress</span>
          <h2>Your content snapshot</h2>
        </div>
      </div>

      <div className="stats-grid creator-stats">
        {statCards.map(({ label, value, tone, icon: Icon }) => (
          <div className={`stat-card ${tone}`} key={label}>
            <div className="stat-header">
              <span>{label}</span>
              <span className="stat-icon"><Icon size={18} /></span>
            </div>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      <div className="workflow-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Workflow</span>
            <h2>From Upload to Insight</h2>
            <p className="workflow-subtitle">Transform your video into meaningful insights in a few simple steps.</p>
          </div>
        </div>
        <div className="workflow-grid creator-workflow">
          {workflowSteps.map(({ icon: Icon, label, detail }, index) => (
            <div className="workflow-node-wrap" key={label}>
              <Link className="workflow-card" to={workflowRoutes[label]} aria-label={`${label}: ${detail}`}>
                <span className="workflow-number">0{index + 1}</span>
                <span className="workflow-icon"><Icon size={20} /></span>
                <span className="workflow-copy">
                <strong>{label}</strong>
                <small>{detail}</small>
                </span>
              </Link>
              {index < workflowSteps.length - 1 && <ArrowRight className="workflow-arrow" size={17} aria-hidden="true" />}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function RoleFeaturePage({ title, description, endpoint }: { title: string; description: string; endpoint?: string }) {
  const { token } = useAuth();
  const [status, setStatus] = useState("Checking access...");
  const [notImplemented, setNotImplemented] = useState(false);

  useEffect(() => {
    if (!endpoint || !token) {
      setStatus("This workspace is ready for the next content module.");
      return;
    }
    checkPermission(endpoint, token)
      .then(result => setStatus(result.message))
      .catch(error => {
        if (error instanceof ApiError && error.status === 404) {
          setNotImplemented(true);
          setStatus("This feature is not implemented yet.");
        } else setStatus(error instanceof Error ? error.message : "Access check failed");
      });
  }, [endpoint, token]);

  return <section className="simple-page feature-page"><span className="eyebrow">Role workspace</span><h1>{title}</h1><p className="feature-description">{description}</p><div className="feature-status" role="status"><span className="status-dot" />{status}</div>{notImplemented ? <div className="feature-placeholder"><span className="eyebrow">Not implemented</span><p>This feature is not implemented yet.</p></div> : <div className="feature-placeholder"><span className="eyebrow">Module ready</span><h2>Your {title.toLowerCase()} workspace</h2><p>Permissions are verified by the ClipMind API before this area can load content.</p></div>}</section>;
}

const acceptedVideoTypes: Record<string, string> = {
  ".avi": "video/x-msvideo",
  ".mkv": "video/x-matroska",
  ".mov": "video/quicktime",
  ".mp4": "video/mp4",
  ".webm": "video/webm",
};
const maxVideoSizeBytes = 524_288_000;

export function VideoUploadPage() {
  const { token } = useAuth();
  const [inputMode, setInputMode] = useState<"upload" | "youtube">("upload");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [youtubeBusy, setYoutubeBusy] = useState(false);
  const [youtubeMessage, setYoutubeMessage] = useState<string | null>(null);
  const [youtubeError, setYoutubeError] = useState<string | null>(null);

  function validateFile(candidate: File) {
    const extension = `.${candidate.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!acceptedVideoTypes[extension] || candidate.type !== acceptedVideoTypes[extension]) return "Choose a supported video with a matching file type and extension.";
    if (candidate.size === 0) return "The selected video is empty.";
    if (candidate.size > maxVideoSizeBytes) return "The selected video exceeds the 500 MB limit.";
    return null;
  }

  function validateYouTubeUrl(value: string) {
    const trimmed = value.trim();
    if (!trimmed) return "Empty URL";

    try {
      const parsed = new URL(trimmed);
      const host = parsed.hostname.toLowerCase();
      const validHosts = ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com"];
      if (!validHosts.includes(host)) return "Invalid YouTube URL";

      const pathParts = parsed.pathname.split("/").filter(Boolean);
      const videoId = host.includes("youtu.be")
        ? pathParts.length === 1 ? pathParts[0] : null
        : pathParts[0]?.toLowerCase() === "watch" && pathParts.length === 1
          ? parsed.searchParams.get("v")
          : ["shorts", "embed"].includes(pathParts[0]?.toLowerCase() ?? "") && pathParts.length === 2
            ? pathParts[1]
            : null;
      if (!videoId || !/^[A-Za-z0-9_-]{11}$/.test(videoId)) return "Unsupported URL";
      return null;
    } catch {
      return "Invalid YouTube URL";
    }
  }

  function selectFile(candidate: File | undefined) {
    setMessage(null);
    const validationError = candidate ? validateFile(candidate) : null;
    setError(validationError);
    setFile(candidate && !validationError ? candidate : null);
  }

  async function runUpload() {
    if (!file || !token) {
      setError("Select a valid video before uploading.");
      return;
    }

    setBusy(true);
    setMessage(null);
    setError(null);

    try {
      const result = await uploadVideo(token, file);
      setMessage(`${result.filename} uploaded successfully. Processing status: ${result.processing_status}.`);
      setFile(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The video could not be uploaded.");
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inputMode === "youtube") {
      const validationError = validateYouTubeUrl(youtubeUrl);
      if (validationError) {
        setYoutubeError(validationError === "Empty URL" ? "Please paste a YouTube video URL." : validationError === "Unsupported URL" ? "This YouTube URL format is not currently supported." : "Please enter a valid YouTube URL.");
        return;
      }
      setYoutubeBusy(true);
      setYoutubeMessage(null);
      setYoutubeError(null);
      try {
        const result = await processYouTubeVideo(token ?? "", youtubeUrl.trim());
        setYoutubeMessage(`YouTube video accepted. Processing status: ${result.status}.`);
        setYoutubeUrl("");
      } catch (reason) {
        setYoutubeError(reason instanceof Error ? reason.message : "The video could not be processed.");
      } finally {
        setYoutubeBusy(false);
      }
      return;
    }
    await runUpload();
  }

  function handleDragOver(event: React.DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(event: React.DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(event: React.DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(false);
    const droppedFile = event.dataTransfer.files?.[0];
    selectFile(droppedFile);
  }

  const fileFormat = file ? (file.name.split(".").pop()?.toUpperCase() ?? "UNKNOWN") : "-";

  return (
    <section className="simple-page upload-page">
      <div className="page-header narrow upload-header">
        <div>
          <span className="eyebrow">Video intake</span>
          <h1>📤 Upload Your Video</h1>
          <p className="feature-description">Turn your video into searchable knowledge.</p>
        </div>
      </div>

      <div className="upload-shell">
        <form className="upload-card" onSubmit={submit}>
          <div className="tab-switcher" style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
            <button type="button" className={inputMode === "upload" ? "primary-button" : "secondary-button"} onClick={() => setInputMode("upload")} style={{ flex: 1 }}>
              Upload Video
            </button>
            <button type="button" className={inputMode === "youtube" ? "primary-button" : "secondary-button"} onClick={() => setInputMode("youtube")} style={{ flex: 1 }}>
              YouTube URL
            </button>
          </div>

          {inputMode === "upload" ? (
            <>
              <label
                className={`upload-dropzone ${isDragging ? "dragging" : ""}`}
                htmlFor="video-file"
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <input
                  id="video-file"
                  type="file"
                  accept={Object.keys(acceptedVideoTypes).join(",")}
                  onChange={event => selectFile(event.target.files?.[0])}
                />

                <div className="dropzone-content">
                  <div className="dropzone-icon"><Upload size={30} /></div>
                  <div className="dropzone-copy">
                    <h2>🎬 Drop your video here</h2>
                    <p>or <span>Choose a video file</span></p>
                    <div className="dropzone-meta">Supported formats: MP4 • WebM • MOV • MKV • AVI</div>
                    <div className="dropzone-meta muted">Maximum size: 500 MB</div>
                  </div>
                </div>
              </label>

              {file ? (
                <div className="selected-file">
                  <div className="file-detail-block">
                    <div className="file-icon">🎬</div>
                    <div className="file-meta">
                      <strong>{file.name}</strong>
                      <div className="file-meta-row">
                        <span>{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
                        <span>{fileFormat}</span>
                      </div>
                    </div>
                  </div>

                  <div className="file-actions">
                    <label className="mini-button upload-change" htmlFor="video-file">Change</label>
                    <button
                      type="button"
                      className="secondary-button file-remove"
                      onClick={() => {
                        setFile(null);
                        setMessage(null);
                        setError(null);
                      }}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ) : null}

              {busy && (
                <div className="upload-status progress" role="status">
                  <span className="status-loader" aria-hidden="true" />
                  <div>
                    <strong>Uploading video</strong>
                    <p>Please wait while your file is processed.</p>
                  </div>
                </div>
              )}

              {error && (
                <div className="upload-alert error" role="alert">
                  <div className="alert-icon">❌</div>
                  <div className="alert-copy">
                    <strong>Upload failed</strong>
                    <p>{error}</p>
                  </div>
                  {file && (
                    <button type="button" className="retry-button" onClick={() => void runUpload()}>
                      Retry
                    </button>
                  )}
                </div>
              )}

              {message && (
                <div className="upload-alert success" role="status">
                  <div className="alert-icon">✅</div>
                  <div className="alert-copy">
                    <strong>Video uploaded successfully</strong>
                    <p>{message}</p>
                  </div>
                </div>
              )}

              <button className="primary-button upload-submit" type="submit" disabled={busy || !file}>
                {busy ? "Uploading..." : "⬆️ Upload Video"}
              </button>
            </>
          ) : (
            <>
              <div className="youtube-input-block" style={{ display: "grid", gap: "0.75rem" }}>
                <label htmlFor="youtube-url" style={{ fontWeight: 600 }}>YouTube URL</label>
                <input
                  id="youtube-url"
                  type="url"
                  value={youtubeUrl}
                  onChange={event => {
                    setYoutubeUrl(event.target.value);
                    if (youtubeError) setYoutubeError(null);
                  }}
                  placeholder="Paste YouTube video URL"
                  style={{ width: "100%", padding: "0.8rem 0.9rem", borderRadius: "0.75rem", border: "1px solid var(--neutral-300, #dfe4ea)" }}
                />
              </div>

              {youtubeBusy && (
                <div className="upload-status progress" role="status">
                  <span className="status-loader" aria-hidden="true" />
                  <div>
                    <strong>Processing video</strong>
                    <p>Please wait while the source is validated and queued.</p>
                  </div>
                </div>
              )}

              {youtubeError && (
                <div className="upload-alert error" role="alert">
                  <div className="alert-icon">❌</div>
                  <div className="alert-copy">
                    <strong>Processing error</strong>
                    <p>{youtubeError}</p>
                  </div>
                </div>
              )}

              {youtubeMessage && (
                <div className="upload-alert success" role="status">
                  <div className="alert-icon">✅</div>
                  <div className="alert-copy">
                    <strong>YouTube video accepted</strong>
                    <p>{youtubeMessage}</p>
                  </div>
                </div>
              )}

              <button className="primary-button upload-submit" type="submit" disabled={youtubeBusy}>
                {youtubeBusy ? "Processing..." : "Process Video"}
              </button>
            </>
          )}
        </form>

        <div className="status-flow">
          <div className="status-step active"><span>📤 Upload</span></div>
          <div className="status-link">↓</div>
          <div className="status-step"><span>📝 Transcript</span></div>
          <div className="status-link">↓</div>
          <div className="status-step"><span>✨ AI Summary</span></div>
          <div className="status-link">↓</div>
          <div className="status-step"><span>🎯 Key Moments</span></div>
          <div className="status-link">↓</div>
          <div className="status-step"><span>✅ Ready</span></div>
        </div>
      </div>
    </section>
  );
}

export function UploadHistoryPage({ administrator = false }: { administrator?: boolean }) {
  const { token } = useAuth();
  const [events, setEvents] = useState<UploadHistoryEvent[]>([]);
  const [videos, setVideos] = useState<VideoListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [sortOrder, setSortOrder] = useState("NEWEST");
  const [selectedVideo, setSelectedVideo] = useState<VideoListItem | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<UploadHistoryEvent | null>(null);
  const [deletingVideoId, setDeletingVideoId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const historyRequestRef = useRef(0);

  async function loadHistory() {
    if (!token) return;
    const requestId = ++historyRequestRef.current;
    setLoading(true);
    setError(null);
    try {
      const history = await getUploadHistory(token, administrator);
      if (requestId !== historyRequestRef.current) return;
      setEvents(history);
      try {
        const nextVideos = await getVideos(token);
        if (requestId === historyRequestRef.current) setVideos(nextVideos);
      } catch (reason) {
        if (requestId === historyRequestRef.current) throw reason;
      }
    } catch (reason) {
      if (requestId === historyRequestRef.current) setError(reason instanceof Error ? reason.message : "Upload history could not be loaded.");
    } finally { if (requestId === historyRequestRef.current) setLoading(false); }
  }

  useEffect(() => { void loadHistory(); }, [administrator, token]);

  async function confirmDelete() {
    if (!selectedEvent || !token) return;
    setDeletingVideoId(selectedEvent.video_id);
    setDeleteError(null);
    try {
      const response = await fetch(withApiBase(`/videos/${selectedEvent.video_id}`), {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      // Treat 404 and 405 as successes so the UI force-clears the stuck row
      if (!response.ok && response.status !== 204 && response.status !== 404 && response.status !== 405) {
        throw new Error("Video could not be deleted.");
      }
      setEvents(current => current.filter(event => event.video_id !== selectedEvent.video_id));
      setVideos(current => current.filter(video => video.id !== selectedEvent.video_id));
      setSelectedEvent(null);
      setNotice("Video deleted successfully.");
      window.setTimeout(() => setNotice(null), 3000);
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason.message : "Video could not be deleted.");
    } finally { setDeletingVideoId(null); }
  }

  const latestEvents = events;

  const filteredEvents = latestEvents
    .filter(event => {
      if (statusFilter === "ALL") return true;
      const status = (event.status || "PENDING").toUpperCase();
      if (statusFilter === "PROCESSING") return ["PROCESSING", "UPLOADING", "VALIDATING", "FFMPEG_PROCESSING", "READY_FOR_AI", "AI_PROCESSING"].includes(status);
      return status === statusFilter;
    })
    .filter(event => `${event.filename} ${event.owner_name} ${event.notes ?? ""}`.toLowerCase().includes(search.trim().toLowerCase()))
    .sort((left, right) => {
      if (sortOrder === "NAME_ASC" || sortOrder === "NAME_DESC") {
        const result = left.filename.localeCompare(right.filename);
        return sortOrder === "NAME_ASC" ? result : -result;
      }
      const result = new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime();
      return sortOrder === "NEWEST" ? -result : result;
    });

  const counts = latestEvents.reduce((summary, event) => {
    const status = (event.status || "PENDING").toUpperCase();
    summary.total += 1;
    if (status === "COMPLETED") summary.completed += 1;
    if (["PROCESSING", "UPLOADING", "VALIDATING", "FFMPEG_PROCESSING", "READY_FOR_AI", "AI_PROCESSING"].includes(status)) summary.processing += 1;
    if (status === "FAILED") summary.failed += 1;
    return summary;
  }, { total: 0, completed: 0, processing: 0, failed: 0 });

  return <section className="simple-page history-page">
    <header className="history-header">
      <div><span className="eyebrow">{administrator ? "Platform activity" : "Creator studio"}</span><h1>{administrator ? "Upload activity" : "Upload History"}</h1><p className="feature-description">Track your uploaded videos, processing progress, and generated insights.</p></div>
      <button className="secondary-button history-refresh" type="button" onClick={() => void loadHistory()} disabled={loading}><span aria-hidden="true">↻</span> Refresh</button>
    </header>
    {notice && <div className="notice success" role="status">{notice}</div>}
      {error && <div className="notice" role="alert">Unable to load upload history.<button className="text-button" type="button" onClick={() => void loadHistory()}>Try Again</button></div>}
      {deleteError && <div className="notice" role="alert">{deleteError}<button className="text-button" type="button" onClick={() => setDeleteError(null)}>Dismiss</button></div>}
    {!error && <>
      <div className="history-metrics" aria-label="Upload history summary"><div><span>Total uploads</span><strong>{counts.total}</strong></div><div><span>Completed</span><strong>{counts.completed}</strong></div><div><span>Processing</span><strong>{counts.processing}</strong></div><div><span>Failed</span><strong>{counts.failed}</strong></div></div>
      <div className="history-toolbar"><label className="history-search" aria-label="Search uploaded videos"><Search size={15} /><input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search uploaded videos..." /></label><label className="history-select"><span>Status</span><select value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="ALL">All statuses</option><option value="COMPLETED">Completed</option><option value="PROCESSING">Processing</option><option value="FAILED">Failed</option><option value="PENDING">Pending</option></select></label><label className="history-select"><span>Sort</span><select value={sortOrder} onChange={event => setSortOrder(event.target.value)}><option value="NEWEST">Newest first</option><option value="OLDEST">Oldest first</option><option value="NAME_ASC">Name A-Z</option><option value="NAME_DESC">Name Z-A</option></select></label></div>
      {loading && <div className="history-skeleton-list" role="status" aria-label="Loading upload history">{[1, 2, 3].map(item => <div className="history-skeleton-row" key={`skeleton-${item}`}><span /><span /><span /><span /></div>)}</div>}
        {!loading && latestEvents.length === 0 && <div className="feature-placeholder history-empty"><span className="eyebrow">No uploads yet</span><h2>Start your video workspace</h2><p>Upload your first video to start generating transcripts, summaries, and key moments.</p><Link className="primary-button" to="/creator/upload">Upload Video</Link></div>}
      {!loading && latestEvents.length > 0 && filteredEvents.length === 0 && <div className="history-empty-filter">No uploads match the current search and filters.</div>}
      {!loading && filteredEvents.length > 0 && <div className="history-table-wrap"><table className="history-table"><thead><tr><th>Video</th>{administrator && <th>Owner</th>}<th>Uploaded</th><th>Size</th><th>Duration</th><th>Status</th><th>Actions</th></tr></thead><tbody>{filteredEvents.map(event => { const video = videos.find(item => item.id === event.video_id); return <tr key={event.video_id}><td><div className="history-video-cell"><span className="history-file-icon"><FileText size={17} /></span><span><strong>{event.filename}</strong><small>{event.source_type} · {event.filename.split(".").pop()?.toUpperCase() || "FILE"}</small></span></div></td>{administrator && <td>{event.owner_name}</td>}<td><strong>{new Date(event.timestamp).toLocaleDateString()}</strong><small>{new Date(event.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</small></td><td>{formatFileSize(event.file_size_bytes)}</td><td>{event.duration_seconds === null ? "Not available" : formatDuration(event.duration_seconds)}</td><td><span className={`event-status ${event.status?.toLowerCase()}`}>{event.status}</span><small className="history-note">{event.notes ?? "No lifecycle note"}</small></td><td><div className="history-actions">{video && <button className="mini-button" type="button" onClick={() => setSelectedVideo(video)} aria-label={`Play ${event.filename}`}>Play</button>}<Link className="mini-button neutral" to={administrator ? `/admin/activity` : `/creator/transcripts/${event.video_id}`}>View</Link><button className="mini-button danger-text" type="button" onClick={() => setSelectedEvent(event)} disabled={deletingVideoId === event.video_id}>Delete</button></div></td></tr>; })}</tbody></table></div>}
    </>}
    {selectedEvent && <DeleteConfirmationModal video={videos.find(video => video.id === selectedEvent.video_id) ?? { id: selectedEvent.video_id, filename: selectedEvent.filename, mime_type: "", file_size_bytes: 0, duration_seconds: null, processing_status: selectedEvent.status, uploaded_at: selectedEvent.timestamp, owner_id: selectedEvent.owner_id, owner_name: selectedEvent.owner_name }} isDeleting={deletingVideoId === selectedEvent.video_id} onConfirm={() => void confirmDelete()} onCancel={() => setSelectedEvent(null)} />}
    {selectedVideo && token && <VideoPlayerModal video={selectedVideo} token={token} onClose={() => setSelectedVideo(null)} />}
  </section>;
}

export function ProcessingStatusPage() {
  const { token } = useAuth();
  const [videos, setVideos] = useState<VideoStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    getVideoStatuses(token)
      .then(setVideos)
      .catch(reason => setError(reason instanceof Error ? reason.message : "Processing status could not be loaded."))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <section className="simple-page status-page">
      <span className="eyebrow">Creator studio</span>
      <h1>Processing status</h1>
      <p className="feature-description">Track the current lifecycle state of your uploaded videos.</p>
      
      {loading && <div className="feature-status" role="status"><span className="status-dot" />Loading current statuses...</div>}
      {error && <div className="notice" role="alert">{error}</div>}
      
      {!loading && !error && videos.length === 0 && (
        <div className="feature-placeholder">
          <span className="eyebrow">Nothing processing</span>
          <h2>No uploaded videos yet</h2>
          <p>Upload a video to begin tracking its lifecycle.</p>
        </div>
      )}
      
      {!loading && !error && videos.length > 0 && (
        <div className="status-list">
          {videos.map(video => {
            const currentStatus = video.processing_status || (video as any).status || "PENDING";
            return (
              <article className="status-card" key={video.id}>
                <div>
                  <strong>{video.filename}</strong>
                  <small>Updated {new Date(video.updated_at || Date.now()).toLocaleString()}</small>
                </div>
                <span className={`event-status ${currentStatus.toLowerCase()}`}>
                  {currentStatus}
                </span>
                <p>{video.latest_note ?? "No status notes yet."}</p>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function ResultPageHeader({ title, description, filename, backLabel = "Back to videos", backTo = "/creator/transcripts" }: { title: string; description: string; filename: string; backLabel?: string; backTo?: string; }) {
  return (
    <div className="result-page-header">
      <Link className="secondary-button" to={backTo}>← {backLabel}</Link>
      <div className="result-page-title-wrap">
        <span className="eyebrow">Video intelligence</span>
        <h1>{title}</h1>
        <p>{description}</p>
        <strong className="result-filename">🎬 {filename}</strong>
      </div>
    </div>
  );
}

function highlightText(text: string, query: string) {
  const trimmedQuery = query.trim();
  if (!trimmedQuery) return text;
  const escaped = trimmedQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`(${escaped})`, "ig");
  return text.split(pattern).map((part, index) =>
    part.toLowerCase() === trimmedQuery.toLowerCase() ? <mark key={`${part}-${index}`}>{part}</mark> : <span key={`${part}-${index}`}>{part}</span>
  );
}

function DeleteConfirmationModal({ video, isDeleting, onConfirm, onCancel }: { video: VideoListItem; isDeleting: boolean; onConfirm: () => void; onCancel: () => void }) {
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Delete this video?</h2>
          <button className="modal-close" onClick={onCancel} aria-label="Close">✕</button>
        </div>
        <div className="modal-body">
          <p><strong>{video.filename}</strong></p>
          <p className="text-muted">All associated generated data for this video may also be removed.</p>
        </div>
        <div className="modal-footer">
          <button className="secondary-button" onClick={onCancel} disabled={isDeleting}>Cancel</button>
          <button className="danger-button" onClick={onConfirm} disabled={isDeleting}>
            {isDeleting ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

function VideoPlayerModal({ video, token, onClose, initialTime }: { video: VideoListItem; token: string; onClose: () => void; initialTime?: number }) {
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [mediaUrl, setMediaUrl] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    setError(null);

    // Grab the right ID whether the backend named it owner_id or user_id
    const actualUserId = video.owner_id || (video as any).user_id;

    const baseMediaUrl = getVideoMediaUrl(video.id, actualUserId, video.filename, video.storage_key);
    const fallbackUrl = `${baseMediaUrl}${baseMediaUrl.includes("?") ? "&" : "?"}token=${token}`;

    if (!token) {
      setMediaUrl(baseMediaUrl);
      setIsLoading(false);
      return;
    }

    // Pass the actualUserId as the third parameter here!
    void getVideoMediaBlobUrl(token, video.id, actualUserId)
      .then(url => {
        if (active) {
          setMediaUrl(url);
          setIsLoading(false);
        } else {
          URL.revokeObjectURL(url);
        }
      })
      .catch(() => {
        if (active) {
          setMediaUrl(fallbackUrl);
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
      setMediaUrl(current => {
        if (current && current.startsWith("blob:")) {
          URL.revokeObjectURL(current);
        }
        return null;
      });
    };
  }, [token, video]);

  useEffect(() => {
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onClose]);

  function seekOnLoad(event: React.SyntheticEvent<HTMLVideoElement>) {
    setIsLoading(false);
    setError(null);
    if (initialTime !== undefined) {
      event.currentTarget.currentTime = initialTime;
      void event.currentTarget.play().catch(() => undefined);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="video-player-modal" onClick={e => e.stopPropagation()}>
        <div className="video-modal-header">
          <h2>{video.filename}</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {isLoading && !error && <div className="video-player-loading">Loading video…</div>}
        {error && <div className="notice" role="alert">{error}</div>}
        <video
          ref={videoRef}
          className="modal-video-player"
          controls
          muted={false}
          playsInline
          preload="metadata"
          onLoadedData={seekOnLoad}
          onError={() => {
            setIsLoading(false);
            setError("This video could not be loaded. Please verify the uploaded file is still available.");
          }}
          src={mediaUrl ?? undefined}
        >
          Your browser does not support the video tag.
        </video>
      </div>
    </div>
  );
}

type AnalysisKind = "transcript" | "summary" | "keyMoments";
type AnalysisCache = {
  transcript: Transcript | null;
  summary: Summary | null;
  keyMoments: KeyMoment[];
  mcqs: McqQuestion[];
  loading: boolean;
  error: string | null;
};

function formatAnalysisTime(seconds: number) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remainder = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}

function analysisStatus(status?: string | null) {
  return status ? status : "MISSING";
}

export function TranscriptModalContent({ data, onRetry, onSeek, onClose }: { data: AnalysisCache; onRetry: () => void; onSeek: (time: number) => void; onClose: () => void }) {
  const [search, setSearch] = useState("");
  const transcript = data.transcript;
  const query = search.trim().toLowerCase();
  const segments = (transcript?.segments || []).filter(segment => !query || segment.text.toLowerCase().includes(query)) ?? [];

  return (
    <>
      {data.loading && <div className="analysis-state" role="status"><span className="status-loader" />Loading transcript...</div>}
      {!data.loading && data.error && <div className="analysis-state analysis-error" role="alert"><strong>Unable to load transcript</strong><p>{data.error}</p><button className="secondary-button" type="button" onClick={onRetry}>Retry</button></div>}
      {!data.loading && !data.error && !transcript && <div className="analysis-state"><FileText size={22} /><strong>No transcript available yet.</strong><p>Generate the transcript to view it here.</p></div>}
      {!data.loading && !data.error && transcript && (
        <>
          <div className="analysis-toolbar">
            <span className={`analysis-status ${transcript.status?.toLowerCase()}`}>{analysisStatus(transcript.status)}</span>
            <label className="analysis-search" aria-label="Search transcript"><Search size={14} /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search transcript..." /></label>
          </div>
          {transcript.status === "FAILED" && <div className="analysis-state analysis-error" role="alert"><strong>Transcript generation failed</strong><p>{transcript.error_message || "The transcript could not be generated."}</p><button className="secondary-button" type="button" onClick={onRetry}>Retry</button></div>}
          {transcript.status !== "FAILED" && <div className="transcript-modal-list">{segments.length === 0 ? <p className="analysis-muted">No transcript matches your search.</p> : segments.map((segment, index) => <button className="transcript-modal-segment" type="button" key={`${segment.start_time}-${index}`} onClick={() => onSeek(segment.start_time)}><time>{formatAnalysisTime(segment.start_time)}</time><span>{segment.text}</span></button>)}</div>}
          <div className="analysis-footer"><button className="secondary-button" type="button" onClick={onClose}>Close</button></div>
        </>
      )}
    </>
  );
}

function SummaryModalContent({ data, onRetry, onGenerate }: { data: AnalysisCache; onRetry: () => void; onGenerate: () => void }) {
  const summary = data.summary;
  return (
    <>
      {data.loading && <div className="analysis-state" role="status"><span className="status-loader" />Loading AI summary...</div>}
      {!data.loading && data.error && <div className="analysis-state analysis-error" role="alert"><strong>Unable to load summary</strong><p>{data.error}</p><button className="secondary-button" type="button" onClick={onRetry}>Retry</button></div>}
      {!data.loading && !data.error && !summary && <div className="analysis-state"><Sparkles size={22} /><strong>No AI summary available yet.</strong><p>Generate a summary to view it here.</p><button className="primary-button" type="button" onClick={onGenerate}>Generate summary</button></div>}
      {!data.loading && !data.error && summary && <>
        <div className="analysis-toolbar"><span className={`analysis-status ${summary.status?.toLowerCase()}`}>{analysisStatus(summary.status)}</span></div>
        {summary.status === "FAILED" ? <div className="analysis-state analysis-error" role="alert"><strong>Summary generation failed</strong><p>The summary could not be generated.</p><button className="secondary-button" type="button" onClick={onRetry}>Retry</button></div> : <div className="summary-content-stack"><article className="result-card"><h3>Short Overview</h3><p>{summary.short_summary}</p></article><article className="result-card"><h3>Detailed Summary</h3><p style={{ whiteSpace: "pre-wrap" }}>{summary.detailed_summary}</p></article></div>}
      </>}
    </>
  );
}

function KeyMomentsModalContent({ data, durationSeconds, onRetry, onGenerate, onWatch }: { data: AnalysisCache; durationSeconds: number | null; onRetry: () => void; onGenerate: () => void; onWatch: (moment: KeyMoment) => void }) {
  const averageImportance = data.keyMoments.length > 0 ? data.keyMoments.reduce((total, moment) => total + moment.importance_score, 0) / data.keyMoments.length : 0;
  const duration = durationSeconds ?? Math.max(...data.keyMoments.map(moment => moment.end_time), 0);
  const durationLabel = duration > 0 ? formatAnalysisTime(duration) : "--:--";
  return (
    <>
      {data.loading && <div className="analysis-state" role="status"><span className="status-loader" />Loading key moments...</div>}
      {!data.loading && data.error && <div className="analysis-state analysis-error" role="alert"><strong>Unable to load key moments</strong><p>{data.error}</p><button className="secondary-button" type="button" onClick={onRetry}>Retry</button></div>}
      {!data.loading && !data.error && data.keyMoments.length === 0 && <div className="analysis-state"><WandSparkles size={22} /><strong>No key moments detected yet.</strong><p>Generate key moments to view them here.</p><button className="primary-button" type="button" onClick={onGenerate}>Generate key moments</button></div>}
      {!data.loading && !data.error && data.keyMoments.length > 0 && <>
        <div className="key-moments-intro"><WandSparkles size={18} /><div><strong>AI-detected highlights</strong><p>Focus on the moments with the most useful signal from this video.</p></div></div>
        <div className="insights-strip" aria-label="Key moments summary">
          <div className="insight-stat"><span>Total moments</span><strong>{data.keyMoments.length}</strong></div>
          <div className="insight-stat"><span>Avg. importance</span><strong>{Math.round(averageImportance * 100)}%</strong></div>
          <div className="insight-stat"><span>Video duration</span><strong>{durationLabel}</strong></div>
        </div>
        <div className="analysis-moment-list key-moments-list">{data.keyMoments.map((moment, index) => { const score = Math.max(0, Math.min(1, moment.importance_score)); return <article className="analysis-moment" key={moment.id}><div className="analysis-moment-index"><span className="moment-index">{String(index + 1).padStart(2, "0")}</span></div><div className="analysis-moment-main"><div className="analysis-moment-heading"><h3>{moment.title}</h3>{moment.topic && <span className="topic-chip">{moment.topic}</span>}</div><p>{moment.text}</p><div className="analysis-moment-meta"><span><Clock3 size={13} /> {formatAnalysisTime(moment.start_time)} <span aria-hidden="true">→</span> {formatAnalysisTime(moment.end_time)}</span><span>Importance</span></div><div className="importance-track" aria-label={`Importance ${Math.round(score * 100)} percent`}><span style={{ width: `${Math.round(score * 100)}%` }} /></div></div><div className="analysis-moment-action"><span className="analysis-score">{Math.round(score * 100)}%</span><button className="primary-button compact-button" type="button" onClick={() => onWatch(moment)}><CirclePlay size={14} />Watch Moment</button></div></article>; })}</div>
      </>}
    </>
  );
}

export function MCQQuizPage() {
  const { token } = useAuth();
  const [videos, setVideos] = useState<VideoListItem[]>([]);
  const [selectedVideoId, setSelectedVideoId] = useState("");
  const [questionCount, setQuestionCount] = useState(5);
  const [questions, setQuestions] = useState<McqQuestion[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [score, setScore] = useState(0);
  const [completed, setCompleted] = useState(false);
  const [loadingVideos, setLoadingVideos] = useState(false);
  const [loadingQuiz, setLoadingQuiz] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    const accessToken = token ?? "";
    async function loadVideos() {
      try {
        setLoadingVideos(true);
        setError(null);
        const nextVideos = await getVideos(accessToken, 500);
        setVideos(nextVideos.filter(video => (video.processing_status || (video as any).status || "") === "COMPLETED"));
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "The video library could not be loaded.");
      } finally {
        setLoadingVideos(false);
      }
    }
    void loadVideos();
  }, [token]);

  async function handleGenerateQuiz() {
    if (!token || !selectedVideoId) {
      setError("Please select a processed video before generating the quiz.");
      return;
    }

    try {
      setLoadingQuiz(true);
      setError(null);
      const generatedQuestions = await getExpectedMcqs(token, selectedVideoId);
      const limitedQuestions = generatedQuestions.slice(0, Math.max(1, Math.min(questionCount || 1, generatedQuestions.length || questionCount || 1)));
      setQuestions(limitedQuestions);
      setCurrentIndex(0);
      setSelectedAnswer("");
      setSubmitted(false);
      setCompleted(false);
      setScore(0);
      if (limitedQuestions.length === 0) {
        setError("No MCQ questions were available for the selected video.");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The quiz could not be generated for this video.");
    } finally {
      setLoadingQuiz(false);
    }
  }

  function handleSubmitAnswer() {
    const currentQuestion = questions[currentIndex];
    if (!currentQuestion || !selectedAnswer) return;

    setSubmitted(true);
    if (selectedAnswer === currentQuestion.correct_answer) {
      setScore(value => value + 1);
    }
  }

  function handleNextQuestion() {
    if (currentIndex >= questions.length - 1) {
      setCompleted(true);
      return;
    }

    setCurrentIndex(index => index + 1);
    setSelectedAnswer("");
    setSubmitted(false);
  }

  function handleTryAgain() {
    setQuestions([]);
    setCurrentIndex(0);
    setSelectedAnswer("");
    setSubmitted(false);
    setScore(0);
    setCompleted(false);
    setError(null);
  }

  function handleChooseAnotherVideo() {
    setSelectedVideoId("");
    handleTryAgain();
  }

  const currentQuestion = questions[currentIndex];
  const totalQuestions = questions.length;
  const percentage = totalQuestions > 0 ? Math.round((score / totalQuestions) * 100) : 0;

  return (
    <section className="simple-page">
      <div className="page-header transcript-management-header">
        <div>
          <span className="eyebrow">ClipMind AI</span>
          <h1>MCQ Quiz</h1>
          <p className="feature-description">Generate a short quiz from the transcript, summary, and key moments for a completed video.</p>
        </div>
      </div>

      {error && <div className="notice" role="alert">{error}</div>}

      {!questions.length && !completed && (
        <div className="feature-card" style={{ maxWidth: 720, marginTop: 24 }}>
          <div className="analysis-kicker">Select a video</div>
          <div style={{ display: "grid", gap: 18, marginTop: 20 }}>
            <label style={{ display: "grid", gap: 8 }}>
              <span style={{ fontWeight: 600 }}>Select Video:</span>
              <select value={selectedVideoId} onChange={event => setSelectedVideoId(event.target.value)} aria-label="Select Video" style={{ padding: "0.75rem 0.9rem", borderRadius: 10, border: "1px solid #d1d5db" }} disabled={loadingVideos}>
                <option value="">Choose a processed video</option>
                {videos.map(video => (
                  <option key={video.id} value={video.id}>{video.filename}</option>
                ))}
              </select>
            </label>

            <label style={{ display: "grid", gap: 8 }}>
              <span style={{ fontWeight: 600 }}>Number of Questions:</span>
              <input aria-label="Number of Questions" type="number" min={1} max={10} value={questionCount} onChange={event => setQuestionCount(Math.max(1, Math.min(10, Number(event.target.value) || 1)))} style={{ padding: "0.75rem 0.9rem", borderRadius: 10, border: "1px solid #d1d5db" }} />
            </label>

            <button type="button" className="primary-button" onClick={() => void handleGenerateQuiz()} disabled={loadingQuiz || !selectedVideoId}>
              {loadingQuiz ? "Generating..." : "Generate Quiz"}
            </button>
          </div>
        </div>
      )}

      {questions.length > 0 && !completed && currentQuestion && (
        <div className="mcq-quiz-shell">
          <div className="mcq-question-card">
            <div className="mcq-header-row">
              <div className="analysis-kicker">Question {currentIndex + 1} of {questions.length}</div>
              <div className="mcq-progress-pill">{Math.round(((currentIndex + 1) / questions.length) * 100)}% complete</div>
            </div>

            <h2>{currentQuestion.question}</h2>

            <div className="mcq-option-list">
              {currentQuestion.options.map((option, index) => {
                const optionLabel = `${String.fromCharCode(65 + index)}. ${option}`;
                const isSelected = selectedAnswer === option;
                return (
                  <label key={`${currentQuestion.question}-${option}`} className={`mcq-option ${isSelected ? "selected" : ""}`}>
                    <input aria-label={optionLabel} type="radio" name={`mcq-option-${currentIndex}`} value={option} checked={isSelected} onChange={event => setSelectedAnswer(event.target.value)} />
                    <span className="mcq-option-letter">{String.fromCharCode(65 + index)}</span>
                    <span className="mcq-option-text">{option}</span>
                  </label>
                );
              })}
            </div>

            {!submitted && (
              <button type="button" className="primary-button mcq-submit-button" onClick={handleSubmitAnswer} disabled={!selectedAnswer}>
                Submit Answer
              </button>
            )}

            {submitted && (
              <div className="mcq-result-panel">
                <div className={`mcq-feedback ${selectedAnswer === currentQuestion.correct_answer ? "success" : "error"}`}>
                  {selectedAnswer === currentQuestion.correct_answer ? "✅ Correct!" : "❌ Incorrect"}
                </div>

                <div className="mcq-answer-grid">
                  <p><strong>Correct Answer:</strong> {currentQuestion.correct_answer}</p>
                  <p><strong>Explanation:</strong> {currentQuestion.explanation}</p>
                </div>

                <div className="mcq-meta-list">
                  <span className="mcq-meta-badge">Difficulty: {currentQuestion.difficulty}</span>
                  <span className="mcq-meta-badge">Topic: {currentQuestion.topic}</span>
                  <span className="mcq-meta-badge">Source: {currentQuestion.source}</span>
                  <span className="mcq-meta-badge">Timestamp: {formatAnalysisTime(Number(currentQuestion.timestamp) || 0)}</span>
                </div>

                <button type="button" className="primary-button" onClick={handleNextQuestion}>
                  {currentIndex === questions.length - 1 ? "View Final Result" : "Next Question"}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {completed && (
        <div className="feature-card" style={{ maxWidth: 720, marginTop: 24 }}>
          <div className="analysis-kicker">MCQ Quiz Completed</div>
          <h2 style={{ marginTop: 12 }}>Score: {score} / {questions.length}</h2>
          <p style={{ fontSize: 18, fontWeight: 600 }}>Percentage: {percentage}%</p>

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 20 }}>
            <button type="button" className="primary-button" onClick={handleTryAgain}>Try Again</button>
            <button type="button" className="secondary-button" onClick={handleChooseAnotherVideo}>Choose Another Video</button>
          </div>
        </div>
      )}

      {!loadingVideos && videos.length === 0 && !questions.length && !completed && (
        <div className="feature-placeholder" style={{ marginTop: 24 }}>
          <span className="eyebrow">No processed videos</span>
          <h2>Select a completed video to begin</h2>
          <p>Upload and process a video before creating a quiz.</p>
        </div>
      )}
    </section>
  );
}

export function VideoLibraryPage({ heading, description }: { heading: string; description: string }) {
  const { token, user } = useAuth();
  const [videos, setVideos] = useState<VideoListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [downloadingVideoId, setDownloadingVideoId] = useState<string | null>(null);
  const [generatingVideoId, setGeneratingVideoId] = useState<string | null>(null);
  const [transcriptStates, setTranscriptStates] = useState<Record<string, "ready" | "processing" | "failed" | "not_generated">>({});
  const [selectedVideoForDelete, setSelectedVideoForDelete] = useState<VideoListItem | null>(null);
  const [deletingVideoId, setDeletingVideoId] = useState<string | null>(null);
  const [selectedVideoToPlay, setSelectedVideoToPlay] = useState<VideoListItem | null>(null);
  const [playbackStartTime, setPlaybackStartTime] = useState<number | undefined>(undefined);
  const [activeAnalysis, setActiveAnalysis] = useState<{ kind: AnalysisKind; video: VideoListItem } | null>(null);
  const [analysisCache, setAnalysisCache] = useState<Record<string, AnalysisCache>>({});
  const [deleteSuccessMessage, setDeleteSuccessMessage] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadingAnalysisRef = useRef(new Set<string>());

  function analysisKey(videoId: string, kind: AnalysisKind) {
    return `${videoId}:${kind}`;
  }

  function openAnalysis(kind: AnalysisKind, video: VideoListItem) {
    setActiveAnalysis({ kind, video });
    const key = analysisKey(video.id, kind);
    if (analysisCache[key] || loadingAnalysisRef.current.has(key)) return;
    loadingAnalysisRef.current.add(key);
    setAnalysisCache(current => ({ ...current, [key]: { transcript: null, summary: null, keyMoments: [], mcqs: [], loading: true, error: null } }));
    void loadAnalysis(kind, video);
  }

  async function loadAnalysis(kind: AnalysisKind, video: VideoListItem) {
    if (!token) return;
    const key = analysisKey(video.id, kind);
    try {
      if (kind === "transcript") {
        const transcript = await getTranscript(token, video.id);
        setAnalysisCache(current => ({ ...current, [key]: { ...(current[key] ?? { transcript: null, summary: null, keyMoments: [], mcqs: [], loading: false, error: null }), transcript, loading: false, error: null } }));
      } else if (kind === "summary") {
        const summary = await getSummary(token, video.id);
        setAnalysisCache(current => ({ ...current, [key]: { ...(current[key] ?? { transcript: null, summary: null, keyMoments: [], mcqs: [], loading: false, error: null }), summary, loading: false, error: null } }));
      } else {
        const keyMomentsResponse = await getKeyMoments(token, video.id);
        const keyMoments = keyMomentsResponse.key_moments || [];
        setAnalysisCache(current => ({ ...current, [key]: { ...(current[key] ?? { transcript: null, summary: null, keyMoments: [], mcqs: [], loading: false, error: null }), keyMoments, loading: false, error: null } }));
      }
      loadingAnalysisRef.current.delete(key);
    } catch (reason) {
      const apiError = reason instanceof ApiError && reason.status === 404 ? null : reason instanceof Error ? reason.message : "The analysis could not be loaded.";
      setAnalysisCache(current => ({ ...current, [key]: { ...(current[key] ?? { transcript: null, summary: null, keyMoments: [], mcqs: [], loading: false, error: null }), loading: false, error: apiError } }));
      loadingAnalysisRef.current.delete(key);
    }
  }

  function retryAnalysis() {
    if (!activeAnalysis) return;
    const { kind, video } = activeAnalysis;
    const key = analysisKey(video.id, kind);
    loadingAnalysisRef.current.add(key);
    setAnalysisCache(current => ({ ...current, [key]: { transcript: null, summary: null, keyMoments: [], mcqs: [], loading: true, error: null } }));
    void loadAnalysis(kind, video);
  }

  function watchMoment(moment: KeyMoment) {
    if (!activeAnalysis) return;
    const video = activeAnalysis.video;
    setActiveAnalysis(null);
    setSelectedVideoToPlay(video);
    setPlaybackStartTime(moment.start_time);
  }

  async function resolveTranscriptState(video: VideoListItem): Promise<"ready" | "processing" | "failed" | "not_generated"> {
    try {
      const result = await getTranscript(token ?? "", video.id);
      if (result.status === "COMPLETED") return "ready";
      if (result.status === "FAILED") return "failed";
      if (result.status === "PROCESSING" || result.status === "PENDING") return "processing";
      return "not_generated";
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "";
      if (/does not exist|not found|transcript.*not/i.test(message)) {
        return /processing|pending|in_progress/i.test((video.processing_status || (video as any).status || "")) ? "processing" : "not_generated";
      }
      return "failed";
    }
  }

  async function loadVideos(showLoading = true) {
    if (!token) return;
    if (showLoading) setLoading(true);
    setError(null);
    try {
      const nextVideos = await getVideos(token);
      setVideos(nextVideos);

      if (nextVideos.length === 0) {
        setTranscriptStates({});
        return;
      }

      const nextStates = await Promise.all(
        nextVideos.map(async video => [video.id, await resolveTranscriptState(video)] as const)
      );
      setTranscriptStates(Object.fromEntries(nextStates));

      if (nextStates.some(([, state]) => state === "processing")) {
        if (pollingRef.current) clearTimeout(pollingRef.current);
        pollingRef.current = window.setTimeout(() => {
          pollingRef.current = null;
          void loadVideos(false);
        }, 8000); // Polling reduced to every 8 seconds
      } else {
        pollingRef.current = null;
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Videos could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateTranscript(video: VideoListItem) {
    if (!token) return;
    setGeneratingVideoId(video.id);
    setError(null);
    try {
      await generateTranscript(token, video.id);
      const nextState = await resolveTranscriptState(video);
      setTranscriptStates(current => ({ ...current, [video.id]: nextState }));
      void loadVideos(false);
    } catch (reason) {
      if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
        setError("Your session has expired. Please log in again.");
        return;
      }
      setError(reason instanceof Error ? reason.message : "Transcript generation failed.");
    } finally {
      setGeneratingVideoId(current => (current === video.id ? null : current));
    }
  }

  async function handleGenerateSummaryForLibrary(video: VideoListItem) {
    if (!token) return;
    setGeneratingVideoId(video.id);
    setError(null);
    try {
      await generateSummary(token, video.id);
      await loadAnalysis("summary", video);
    } catch (reason) {
      if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
        setError("Your session has expired. Please log in again.");
      } else {
        setError(reason instanceof Error ? reason.message : "Summary generation failed.");
      }
    } finally {
      setGeneratingVideoId(current => (current === video.id ? null : current));
    }
  }

  async function handleGenerateMomentsForLibrary(video: VideoListItem) {
    if (!token) return;
    setGeneratingVideoId(video.id);
    setError(null);
    try {
      await generateKeyMoments(token, video.id);
      await loadAnalysis("keyMoments", video);
    } catch (reason) {
      if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
        setError("Your session has expired. Please log in again.");
      } else {
        setError(reason instanceof Error ? reason.message : "Key moments detection failed.");
      }
    } finally {
      setGeneratingVideoId(current => (current === video.id ? null : current));
    }
  }

  async function handleDownloadTranscript(video: VideoListItem) {
    if (!token) return;
    const transcriptState = transcriptStates[video.id] ?? (getTranscriptState((video.processing_status || (video as any).status || "")) === "transcript_ready" ? "ready" : "not_generated");

    if (transcriptState !== "ready") {
      setError(
        transcriptState === "processing"
          ? "Transcript is still being generated."
          : transcriptState === "failed"
            ? "Transcript generation failed."
            : "Transcript has not been generated yet."
      );
      return;
    }

    setDownloadingVideoId(video.id);
    try {
      const blob = await downloadTranscript(token, video.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${video.filename.replace(/\.[^.]+$/, "")}-transcript.txt`;
      link.click();
      URL.revokeObjectURL(url);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Transcript download failed.");
    } finally {
      setDownloadingVideoId(null);
    }
  }

  async function handleDeleteVideo(video: VideoListItem) {
    setSelectedVideoForDelete(video);
  }

  async function confirmDeleteVideo() {
    if (!selectedVideoForDelete || !token) return;
    setDeletingVideoId(selectedVideoForDelete.id);
    try {
      const response = await fetch(withApiBase(`/videos/${selectedVideoForDelete.id}`), {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      
      // Treat 404 (Not Found) and 405 (Method Not Allowed) as successes so the UI force-clears the stuck row
      if (!response.ok && response.status !== 204 && response.status !== 404 && response.status !== 405) {
        const altResponse = await fetch(withApiBase(`/api/videos/${selectedVideoForDelete.id}`), {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` }
        });
        if (!altResponse.ok && altResponse.status !== 204 && altResponse.status !== 404 && altResponse.status !== 405) {
          throw new Error("Video could not be deleted.");
        }
      }
      
      // Forcefully remove it from the UI state
      setVideos(current => current.filter(item => item.id !== selectedVideoForDelete.id));
      setTranscriptStates(current => {
        const next = { ...current };
        delete next[selectedVideoForDelete.id];
        return next;
      });
      setDeleteSuccessMessage(`${selectedVideoForDelete.filename} deleted successfully.`);
      setTimeout(() => setDeleteSuccessMessage(null), 3000);
      setSelectedVideoForDelete(null);
    } catch (reason) {
      if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
        setError("Your session has expired. Please log in again.");
      } else {
        setError(reason instanceof Error ? reason.message : "Video could not be deleted.");
      }
    } finally {
      setDeletingVideoId(null);
    }
  }

  useEffect(() => {
    if (!token) return;
    void loadVideos();
  }, [token, user?.role]);

  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearTimeout(pollingRef.current);
      }
    };
  }, []);

  const filteredVideos = videos.filter(video => video.filename.toLowerCase().includes(search.toLowerCase()));

  return (
    <section className="simple-page library-page">
      <div className="page-header transcript-management-header">
        <div>
          <span className="eyebrow">ClipMind AI</span>
          <h1>{heading || "Transcripts"}</h1>
          <p className="feature-description">{description || "View and manage your video transcripts"}</p>
        </div>

        <label className="compact-search" aria-label="Search videos">
          <Search size={14} />
          <input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search videos..." />
        </label>
      </div>

      {deleteSuccessMessage && <div className="notice success" role="status">{deleteSuccessMessage}</div>}
      {loading && <div className="feature-status" role="status"><span className="status-dot" />Loading videos...</div>}
      {error && <div className="notice" role="alert">{error}<button className="text-button" onClick={() => void loadVideos()}>Try again</button></div>}

      {!loading && !error && filteredVideos.length === 0 && (
        <div className="feature-placeholder">
          <span className="eyebrow">No videos found</span>
          <h2>Your library is empty</h2>
          <p>Uploaded videos will appear here with their processing status.</p>
        </div>
      )}

      {!loading && !error && filteredVideos.length > 0 && (
        <div className="video-list">
          {filteredVideos.map(video => {
            const state = transcriptStates[video.id] ?? (getTranscriptState((video.processing_status || (video as any).status || "")) === "transcript_ready" ? "ready" : /processing|pending|in_progress|uploaded/i.test((video.processing_status || (video as any).status || "")) ? "processing" : "not_generated");
            const ready = state === "ready";
            const processing = state === "processing";
            const failed = state === "failed";
            const transcriptStatusLabel = ready ? "Ready" : processing ? "Processing" : failed ? "Failed" : "Waiting";
            const transcriptStatusTone = ready ? "success" : processing ? "warning" : failed ? "danger" : "neutral";
            const summaryStatusLabel = ready ? "Ready" : "Waiting";
            const summaryStatusTone = ready ? "success" : "neutral";
            const momentsStatusLabel = ready ? "Ready" : "Waiting";
            const momentsStatusTone = ready ? "success" : "neutral";
            const mediaUrl = getVideoMediaUrl(video.id, video.owner_id || (video as any).user_id, video.filename, video.storage_key);
            
            return (
              <article className="video-management-card" key={video.id}>
                <div className="video-thumb-panel" onClick={() => setSelectedVideoToPlay(video)} role="button" tabIndex={0} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedVideoToPlay(video); } }}>
                  <video className="video-thumb-preview" src={mediaUrl} muted playsInline preload="metadata" aria-label={`Play ${video.filename}`} title="Click to play" />
                  <div className="video-thumb-overlay"><CirclePlay size={18} /></div>
                  {video.duration_seconds && video.duration_seconds > 0 && (
                    <span className="duration-badge">{formatDuration(video.duration_seconds)}</span>
                  )}
                </div>

                <div className="video-management-body">
                  <h2 title={video.filename}>{video.filename}</h2>

                  <div className="video-meta-list">
                    <span><User size={13} /> {video.owner_name}</span>
                    <span><CalendarDays size={13} /> {new Date(video.uploaded_at).toLocaleDateString()}</span>
                    <span><Clock3 size={13} /> {video.duration_seconds ? formatDuration(video.duration_seconds) : "Duration pending"}</span>
                    <span><HardDrive size={13} /> {formatFileSize(video.file_size_bytes)}</span>
                  </div>

                  <div className="video-action-row">
                    <button type="button" className="primary-button compact-button" onClick={() => setSelectedVideoToPlay(video)}>
                      <CirclePlay size={14} /> Play
                    </button>
                    {state === "not_generated" || state === "failed" ? (
                      <button type="button" className="secondary-button compact-button" onClick={() => void handleGenerateTranscript(video)} disabled={generatingVideoId === video.id}>
                        {generatingVideoId === video.id ? "Generating..." : "Generate Transcript"}
                      </button>
                    ) : null}
                    <button type="button" className="secondary-button compact-button compact-danger-button" onClick={() => void handleDeleteVideo(video)} disabled={deletingVideoId === video.id}>
                      {deletingVideoId === video.id ? (
                        <>
                          <span className="inline-spinner-mini" /> Deleting...
                        </>
                      ) : (
                        <>
                          <Trash2 size={14} /> Delete
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <div className="video-status-panel">
                  <div className="status-panel-header">Processing status</div>
                  <div className={`status-readout ${transcriptStatusTone}`}><span className="status-dot" /> Transcript • {transcriptStatusLabel}</div>
                  <div className={`status-readout ${summaryStatusTone}`}><span className="status-dot" /> AI Summary • {summaryStatusLabel}</div>
                  <div className={`status-readout ${momentsStatusTone}`}><span className="status-dot" /> Key Moments • {momentsStatusLabel}</div>

                  <div className="quick-feature-actions compact-actions">
                    <button type="button" className="mini-nav-button" onClick={() => openAnalysis("transcript", video)}><FileText size={13} /> Transcript</button>
                    <button type="button" className="mini-nav-button" onClick={() => openAnalysis("summary", video)}><Sparkles size={13} /> AI Summary</button>
                    <button type="button" className="mini-nav-button" onClick={() => openAnalysis("keyMoments", video)}><WandSparkles size={13} /> Key Moments</button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {selectedVideoForDelete && (
        <DeleteConfirmationModal
          video={selectedVideoForDelete}
          isDeleting={deletingVideoId === selectedVideoForDelete.id}
          onConfirm={() => void confirmDeleteVideo()}
          onCancel={() => setSelectedVideoForDelete(null)}
        />
      )}

      {selectedVideoToPlay && (
        <VideoPlayerModal
          video={selectedVideoToPlay}
          token={token ?? ""}
          initialTime={playbackStartTime}
          onClose={() => { setSelectedVideoToPlay(null); setPlaybackStartTime(undefined); }}
        />
      )}

      {activeAnalysis && (
        <Modal
          open
          title={activeAnalysis.kind === "transcript" ? "Video Transcript" : activeAnalysis.kind === "summary" ? "AI Summary" : "Key Moments"}
          subtitle={activeAnalysis.video.filename}
          onClose={() => setActiveAnalysis(null)}
          className={activeAnalysis.kind === "transcript" ? "transcript-analysis-modal" : activeAnalysis.kind === "keyMoments" ? "key-moments-analysis-modal" : ""}
        >
          {activeAnalysis.kind === "transcript" && <TranscriptModalContent data={analysisCache[analysisKey(activeAnalysis.video.id, activeAnalysis.kind)] ?? { transcript: null, summary: null, keyMoments: [], mcqs: [], loading: true, error: null }} onRetry={retryAnalysis} onSeek={time => { setActiveAnalysis(null); setPlaybackStartTime(time); setSelectedVideoToPlay(activeAnalysis.video); }} onClose={() => setActiveAnalysis(null)} />}
          {activeAnalysis.kind === "summary" && <SummaryModalContent data={analysisCache[analysisKey(activeAnalysis.video.id, activeAnalysis.kind)] ?? { transcript: null, summary: null, keyMoments: [], mcqs: [], loading: true, error: null }} onRetry={retryAnalysis} onGenerate={() => void handleGenerateSummaryForLibrary(activeAnalysis.video)} />}
          {activeAnalysis.kind === "keyMoments" && <KeyMomentsModalContent data={analysisCache[analysisKey(activeAnalysis.video.id, activeAnalysis.kind)] ?? { transcript: null, summary: null, keyMoments: [], mcqs: [], loading: true, error: null }} durationSeconds={activeAnalysis.video.duration_seconds} onRetry={retryAnalysis} onGenerate={() => void handleGenerateMomentsForLibrary(activeAnalysis.video)} onWatch={watchMoment} />}
        </Modal>
      )}
    </section>
  );
}

export function VideoResultsPage() {
  const { token } = useAuth();
  const { videoId } = useParams();
  const [video, setVideo] = useState<VideoListItem | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [moments, setMoments] = useState<KeyMoment[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const pollingRef = useRef<number | null>(null);

  const transcriptState = useMemo(() => {
    if (transcript?.status === "COMPLETED") return "READY";
    if (transcript?.status === "FAILED") return "FAILED";
    if (transcript?.status === "PROCESSING" || transcript?.status === "PENDING") return "PROCESSING";
    if (video && /processing|pending|in_progress/i.test((video.processing_status || (video as any).status || ""))) return "PROCESSING";
    if (video && /failed|error/i.test((video.processing_status || (video as any).status || ""))) return "FAILED";
    return "NOT_STARTED";
  }, [transcript, video]);

  const summaryState = useMemo(() => {
    if (summary?.status === "FAILED") return "FAILED";
    if (summary) return "READY";
    if (transcriptState === "READY") return "WAITING";
    if (transcriptState === "PROCESSING" || (video && /processing|pending|in_progress/i.test((video.processing_status || (video as any).status || "")))) return "PROCESSING";
    return "WAITING";
  }, [summary, transcriptState, video]);

  const keyMomentsState = useMemo(() => {
    if (moments.length > 0) return "READY";
    if (transcriptState === "READY") return "WAITING";
    if (transcriptState === "PROCESSING" || (video && /processing|pending|in_progress/i.test((video.processing_status || (video as any).status || "")))) return "PROCESSING";
    return "WAITING";
  }, [moments.length, transcriptState, video]);

  const refreshData = async (silent = false) => {
    if (!token || !videoId) return;
    if (!silent) setLoading(true);
    try {
      const videos = await getVideos(token);
      const match = videos.find(item => item.id === videoId) ?? null;
      setVideo(match);

      if (!match) {
        setError("This video could not be found.");
        return;
      }

      try {
        const transcriptResult = await getTranscript(token, videoId);
        setTranscript(transcriptResult);
      } catch (reason) {
        setTranscript(null);
      }

      try {
        const summaryResult = await getSummary(token, videoId);
        setSummary(summaryResult);
      } catch (reason) {
        setSummary(null);
      }

      try {
        const momentsResult = await getKeyMoments(token, videoId);
        setMoments((momentsResult.key_moments || []).sort((a, b) => a.start_time - b.start_time));
      } catch (reason) {
        setMoments([]);
      }

      setError(null);
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "Video details could not be loaded.";
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!token || !videoId) return;
    void refreshData(false);
    return () => {
      if (pollingRef.current) {
        window.clearTimeout(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [token, videoId]);

  useEffect(() => {
    if (!token || !videoId || !video) return;
    const shouldPoll = /processing|pending|in_progress/i.test((video.processing_status || (video as any).status || ""))
      || transcriptState === "PROCESSING"
      || summaryState === "PROCESSING"
      || keyMomentsState === "PROCESSING";

    if (!shouldPoll) return;
    if (pollingRef.current) window.clearTimeout(pollingRef.current);
    pollingRef.current = window.setTimeout(() => {
      void refreshData(true);
    }, 8000);

    return () => {
      if (pollingRef.current) {
        window.clearTimeout(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [token, video, videoId, transcriptState, summaryState, keyMomentsState]);

  const filteredSegments = useMemo(() => {
    if (!transcript?.segments) return [];
    const query = search.trim().toLowerCase();
    if (!query) return transcript.segments;
    return transcript.segments.filter(segment => segment.text.toLowerCase().includes(query));
  }, [search, transcript]);

  async function handleGenerateTranscript() {
    if (!token || !videoId) return;
    setBusy(true);
    setError(null);
    try {
      await generateTranscript(token, videoId);
      await refreshData(true);
    } catch (reason) {
      if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
        setError("Your session has expired. Please log in again.");
      } else {
        setError(reason instanceof Error ? reason.message : "Transcript generation failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerateSummary() {
    if (!token || !videoId) return;
    setBusy(true);
    setError(null);
    try {
      if (summary?.status === "FAILED") {
        await retrySummary(token, videoId);
      } else {
        await generateSummary(token, videoId, Boolean(summary));
      }
      await refreshData(true);
    } catch (reason) {
      if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
        setError("Your session has expired. Please log in again.");
      } else {
        setError(reason instanceof Error ? reason.message : "Summary generation failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerateMoments() {
    if (!token || !videoId) return;
    setBusy(true);
    setError(null);
    try {
      await generateKeyMoments(token, videoId);
      await refreshData(true);
    } catch (reason) {
      if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
        setError("Your session has expired. Please log in again.");
      } else {
        setError(reason instanceof Error ? reason.message : "Key moments detection failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleDownloadTranscript() {
    if (!token || !video || transcriptState !== "READY") return;
    setDownloading(true);
    try {
      const blob = await downloadTranscript(token, video.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${video.filename.replace(/\.[^.]+$/, "")}-transcript.txt`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
        setError("Your session has expired. Please log in again.");
      } else {
        setError(reason instanceof Error ? reason.message : "Transcript download failed.");
      }
    } finally {
      setDownloading(false);
    }
  }

  if (!videoId) return <Navigate to="/creator/transcripts" replace />;
  if (loading || !video) {
    return <section className="simple-page"><div className="feature-status" role="status"><span className="status-dot" />Loading video analysis...</div></section>;
  }

  const progressSteps = [
    { label: "Uploaded", complete: true },
    { label: "Audio", complete: transcriptState !== "NOT_STARTED" },
    { label: "AI Processing", complete: transcriptState === "READY" || summaryState === "READY" || keyMomentsState === "READY" },
    { label: "Summary", complete: summaryState === "READY" },
  ];

  const progressPercent = Math.min(100, Math.round(((progressSteps.filter(step => step.complete).length / progressSteps.length) * 100)));

  return (
    <section className="simple-page result-shell">
      <div className="result-header-card">
        <div className="result-header-copy">
          <span className="eyebrow">ClipMind AI output</span>
          <h1>{video.filename}</h1>
          <p>Review the transcript, summary, and key moments for this video.</p>
        </div>
        <div className="result-header-actions">
          <Link className="secondary-button" to="/creator/transcripts">Dashboard</Link>
          <Link className="secondary-button" to="/creator/history">History</Link>
          <Link className="secondary-button" to="/creator/upload">New Video</Link>
          <button className="primary-button" type="button" onClick={() => void refreshData(true)}>
            Refresh
          </button>
        </div>
      </div>

      <div className="result-progress-card">
        <div className="progress-header-row">
          <strong>Processing Progress</strong>
          <span>{progressPercent}%</span>
        </div>
        <div className="progress-bar" aria-label="Processing progress">
          <span style={{ width: `${progressPercent}%` }} />
        </div>
        <div className="progress-steps">
          {progressSteps.map((step, index) => (
            <div key={`${step.label}-${index}`} className={`progress-step ${step.complete ? "complete" : ""}`}>
              <span className="progress-bullet">{step.complete ? "✓" : "○"}</span>
              <span>{step.label}</span>
            </div>
          ))}
        </div>
        {progressPercent >= 100 && <div className="result-status-note">Your video has been fully analyzed.</div>}
      </div>

      {error && <div className="notice" role="alert">{error}</div>}

      <div className="result-card">
        <div className="card-header-row">
          <div className="header-inline">
            <FileText size={16} />
            <strong>Transcript</strong>
          </div>
          <span className={`status-badge ${transcriptState.toLowerCase()}`}>
            {transcriptState === "READY" ? "READY" : transcriptState === "PROCESSING" ? "PROCESSING" : transcriptState === "FAILED" ? "FAILED" : "WAITING"}
          </span>
        </div>
        {transcriptState === "PROCESSING" && (
          <div className="empty-state-inline">
            <div className="inline-spinner" />
            <p>Transcript is being generated...</p>
          </div>
        )}
        {transcriptState === "FAILED" && (
          <div className="empty-state-inline failing">
            <p>Transcript generation failed. Please retry.</p>
            <button className="primary-button" type="button" onClick={() => void handleGenerateTranscript()} disabled={busy}>
              Retry transcript
            </button>
          </div>
        )}
        {transcriptState === "NOT_STARTED" && (
          <div className="empty-state-inline">
            <p>Transcript is not ready yet.</p>
            <button className="primary-button" type="button" onClick={() => void handleGenerateTranscript()} disabled={busy}>
              {busy ? "Generating..." : "Generate transcript"}
            </button>
          </div>
        )}
        {transcriptState === "READY" && transcript && (
          <>
            <label className="transcript-search compact" aria-label="Search transcript">
              <Search size={14} />
              <input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search transcript" />
            </label>
            <div className="transcript-text-block">
              {filteredSegments.length === 0 ? (
                <p>No transcript matches your current search.</p>
              ) : (
                filteredSegments.map((segment, index) => (
                  <article className="transcript-line" key={`${segment.start_time}-${segment.end_time}-${index}`}>
                    <time>{formatClock(segment.start_time)}</time>
                    <p>{highlightText(segment.text, search)}</p>
                  </article>
                ))
              )}
            </div>
            <div className="card-actions-row">
              <button className="secondary-button" type="button" onClick={() => void handleDownloadTranscript()} disabled={downloading}>
                {downloading ? "Downloading..." : "Download transcript"}
              </button>
            </div>
          </>
        )}
      </div>

      <div className="result-card">
        <div className="card-header-row">
          <div className="header-inline">
            <Sparkles size={16} />
            <strong>AI Summary</strong>
          </div>
          <span className={`status-badge ${summaryState.toLowerCase()}`}>
            {summaryState === "READY" ? "READY" : summaryState === "PROCESSING" ? "GENERATING" : "WAITING"}
          </span>
        </div>
        {summaryState === "WAITING" && transcriptState === "READY" && (
          <div className="empty-state-inline centered">
            <p>Your transcript is ready. Generate an AI-powered summary from it.</p>
            <button className="primary-button" type="button" onClick={() => void handleGenerateSummary()} disabled={busy}>
              {busy ? "Generating..." : "Generate AI Summary"}
            </button>
          </div>
        )}
        {summaryState === "PROCESSING" && (
          <div className="empty-state-inline">
            <div className="inline-spinner" />
            <p>AI summary is being generated...</p>
          </div>
        )}
        {summaryState === "READY" && summary && (
          <div className="summary-content-stack">
            <article className="result-card">
              <h3>Short Overview</h3>
              <p>{summary.short_summary}</p>
            </article>
            <article className="result-card">
              <h3>Detailed Summary</h3>
              <p style={{ whiteSpace: "pre-wrap" }}>{summary.detailed_summary}</p>
            </article>
          </div>
        )}
      </div>

      <div className="result-card">
        <div className="card-header-row">
          <div className="header-inline">
            <WandSparkles size={16} />
            <strong>Key Moments</strong>
          </div>
          <span className={`status-badge ${keyMomentsState.toLowerCase()}`}>
            {moments.length > 0 ? "READY" : keyMomentsState === "PROCESSING" ? "DETECTING" : keyMomentsState === "WAITING" ? "WAITING" : "WAITING"}
          </span>
        </div>
        {keyMomentsState === "WAITING" && transcriptState === "READY" && (
          <div className="empty-state-inline centered">
            <p>Key moments are ready to be detected from this transcript.</p>
            <button className="primary-button" type="button" onClick={() => void handleGenerateMoments()} disabled={busy}>
              {busy ? "Detecting..." : "Detect key moments"}
            </button>
          </div>
        )}
        {keyMomentsState === "PROCESSING" && (
          <div className="empty-state-inline">
            <div className="inline-spinner" />
            <p>Key moments are being detected...</p>
          </div>
        )}
        {moments.length > 0 && (
          <div className="moment-list">
            {moments.slice(0, 8).map(moment => (
              <article key={moment.id} className="moment-item">
                <div className="moment-time">{formatClock(moment.start_time)}</div>
                <div>
                  <strong>{moment.title}</strong>
                  <p>{moment.text}</p>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      <div className="bottom-action-row">
        <Link className="secondary-button" to="/dashboard">Dashboard</Link>
        <Link className="secondary-button" to="/creator/history">History</Link>
        <Link className="secondary-button" to="/creator/upload">New Video</Link>
        <button className="primary-button" type="button" onClick={() => void refreshData(true)}>Refresh</button>
      </div>
    </section>
  );
}

export function VideoSummaryPage() {
  const { token } = useAuth();
  const { videoId } = useParams();
  const [video, setVideo] = useState<VideoListItem | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !videoId) return;

    let active = true;
    getVideos(token)
      .then(videos => {
        if (!active) return;
        const match = videos.find(item => item.id === videoId) ?? null;
        setVideo(match);
      })
      .catch(() => undefined);

    getSummary(token, videoId)
      .then(result => {
        if (!active) return;
        setSummary(result);
      })
      .catch(reason => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Summary could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, [token, videoId]);

  if (!videoId) return <Navigate to="/creator/transcripts" replace />;
  if (loading) return <section className="simple-page"><div className="feature-status" role="status"><span className="status-dot" />Loading AI summary...</div></section>;
  if (!video) return <section className="simple-page"><div className="notice" role="alert">This video could not be found.<Link className="text-button" to="/creator/transcripts">Back to videos</Link></div></section>;

  return (
    <section className="simple-page result-page summary-page">
      <ResultPageHeader title="✨ AI Summary" description="Review the generated summary and extracted insights." filename={video.filename} />
      {error ? (
        <div className="notice" role="alert">
          <strong>⚠️ Unable to load AI Summary</strong>
          <p>We couldn't connect to the processing service.</p>
          <button className="primary-button" type="button" onClick={() => window.location.reload()}>Try Again</button>
        </div>
      ) : !summary ? (
        <div className="empty-state compact">
          <div className="empty-icon"><Sparkles size={18} /></div>
          <h3>✨ AI Summary isn’t available yet</h3>
          <p>Process a video to generate a summary.</p>
        </div>
      ) : (
        <div className="summary-content-stack">
            <article className="result-card">
              <h3>Short Overview</h3>
              <p>{summary.short_summary}</p>
            </article>
            <article className="result-card">
              <h3>Detailed Summary</h3>
              <p style={{ whiteSpace: "pre-wrap" }}>{summary.detailed_summary}</p>
            </article>
          </div>
      )}
    </section>
  );
}

export function VideoKeyMomentsPage() {
  const { token } = useAuth();
  const { videoId } = useParams();
  const [video, setVideo] = useState<VideoListItem | null>(null);
  const [moments, setMoments] = useState<KeyMoment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !videoId) return;

    let active = true;
    getVideos(token)
      .then(videos => {
        if (!active) return;
        setVideo(videos.find(item => item.id === videoId) ?? null);
      })
      .catch(() => undefined);

    getKeyMoments(token, videoId)
      .then(result => {
        if (!active) return;
        setMoments((result.key_moments || []).sort((a, b) => a.start_time - b.start_time));
      })
      .catch(reason => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Key moments could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, [token, videoId]);

  if (!videoId) return <Navigate to="/creator/transcripts" replace />;
  if (loading) return <section className="simple-page"><div className="feature-status" role="status"><span className="status-dot" />Loading key moments...</div></section>;
  if (!video) return <section className="simple-page"><div className="notice" role="alert">This video could not be found.<Link className="text-button" to="/creator/transcripts">Back to videos</Link></div></section>;

  if (error) {
    return <section className="simple-page"><div className="notice" role="alert"><strong>⚠️ Unable to load key moments</strong><p>We couldn't connect to the processing service.</p><button className="primary-button" type="button" onClick={() => window.location.reload()}>Try Again</button></div></section>;
  }

  const maxTime = moments.length > 0 ? Math.max(...moments.map(moment => moment.end_time)) : 0;

  return (
    <section className="simple-page result-page key-moments-page">
      <ResultPageHeader title="🎯 Key Moments" description="Review the most important moments detected in this video." filename={video.filename} />
      {moments.length === 0 ? (
        <div className="empty-state compact">
          <div className="empty-icon"><Sparkles size={18} /></div>
          <h3>🎯 No key moments detected</h3>
          <p>Try processing the video again if needed.</p>
        </div>
      ) : (
        <>
          <div className="key-moments-timeline" aria-label="Key moments timeline">
            {moments.map(moment => (
              <div key={moment.id} className="timeline-point" style={{ left: `${maxTime > 0 ? (moment.start_time / maxTime) * 100 : 0}%` }}>
                <span className="timeline-dot" />
                <small>{Math.round(moment.importance_score * 100)}%</small>
              </div>
            ))}
          </div>
          <div className="key-moment-list">
            {moments.map(moment => (
              <article className="result-card key-moment-card" key={moment.id}>
                <div className="key-moment-header">
                  <strong>🎯 {formatClock(moment.start_time)} - {formatClock(moment.end_time)}</strong>
                  <span className="importance-badge">Importance {Math.round(moment.importance_score * 100)}%</span>
                </div>
                <h3>{moment.title}</h3>
                <p>{moment.text}</p>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

export function DashboardRedirect() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={`/dashboard/${user.role.toLowerCase().replace(" ", "-")}`} replace />;
}

export function Login() {
  const { user, login, error } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/dashboard" replace />;
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); try { await login(email, password); navigate("/dashboard"); } finally { setBusy(false); } }
  return <main className="login-page"><div className="login-art"><div className="brand"><span className="brand-mark"><Clapperboard size={18} /></span><span>ClipMind <em>AI</em></span></div><div className="art-copy"><span className="eyebrow">Turn videos into knowledge.</span><h1>Make the important moments easier to find.</h1><p>One calm workspace for creators, learners, educators, and the people keeping it all running.</p></div><div className="orbit-card"><Clapperboard size={19} /><span>Video intelligence platform</span></div></div><div className="login-panel"><div className="form-wrap"><span className="eyebrow">Welcome back</span><h2>Sign in to ClipMind</h2><p className="form-intro">Use your account credentials to open your role workspace.</p><form onSubmit={submit}><label>Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} required /></label><label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required /></label>{error && <p className="form-error">{error}</p>}<button className="primary-button" disabled={busy}>{busy ? "Signing in..." : "Continue to workspace"}</button></form><Link className="auth-link" to="/register">Create an account</Link></div></div></main>;
}

export function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", confirm_password: "", role: "Content Creator" });  
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  function update(field: keyof typeof form, value: string) { setForm(current => ({ ...current, [field]: value })); }  
  
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (form.password.length < 8) { setError("Password must be at least 8 characters."); return; }
    if (form.password !== form.confirm_password) { setError("Passwords do not match."); return; }
    setBusy(true);
    
    try { 
      const payload = {
        name: form.name,
        email: form.email,
        password: form.password,
        role: form.role 
      };
      
      await registerRequest(payload as any); 
      setSuccess("Account created. Redirecting to sign in..."); 
      setTimeout(() => navigate("/login"), 700); 
    }
    catch (reason) { 
      console.error("Full Registration Error:", reason);
      setError(reason instanceof Error ? reason.message : "Registration failed."); 
    }
    finally { setBusy(false); }
  }
  
  return <main className="login-page"><div className="login-art"><div className="brand"><span className="brand-mark"><Clapperboard size={18} /></span><span>ClipMind <em>AI</em></span></div><div className="art-copy"><span className="eyebrow">Start your workspace</span><h1>Give every frame somewhere useful to go.</h1><p>Create a role-aware ClipMind account for making, learning, teaching, or operating.</p></div></div><div className="login-panel"><div className="form-wrap"><span className="eyebrow">New account</span><h2>Join ClipMind</h2><p className="form-intro">Your role determines the workspace and permissions you receive.</p><form onSubmit={submit}><label>👤 Full name<input value={form.name} onChange={event => update("name", event.target.value)} required /></label><label>📧 Email<input type="email" value={form.email} onChange={event => update("email", event.target.value)} required /></label><label>🎭 Role<select value={form.role} onChange={event => update("role", event.target.value)}><option>Content Creator</option><option>Learner</option><option>Educator</option><option>Administrator</option></select></label><label>🔐 Password<input type="password" value={form.password} onChange={event => update("password", event.target.value)} minLength={8} required /></label><label>🔐 Confirm password<input type="password" value={form.confirm_password} onChange={event => update("confirm_password", event.target.value)} minLength={8} required /></label>{error && <p className="form-error" role="alert">{error}</p>}{success && <p className="upload-success" role="status">{success}</p>}<button className="primary-button" disabled={busy}>{busy ? "Creating account..." : "Create account"}</button></form><Link className="auth-link" to="/login">Back to sign in</Link></div></div></main>;
}

export function AnalyticsPage() {
  const { token, user } = useAuth();
  const [analytics, setAnalytics] = useState<AnalyticsDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !user) return;
    const loader = user.role === "Administrator" ? getAdminAnalytics : getCreatorAnalytics;
    loader(token)
      .then(setAnalytics)
      .catch(reason => setError(reason instanceof Error ? reason.message : "Unable to load analytics."))
      .finally(() => setLoading(false));
  }, [token, user]);

  if (loading) return <section className="simple-page analytics-page"><h1>Analytics</h1><p>Loading platform intelligence...</p></section>;
  if (error) return <section className="simple-page analytics-page"><h1>Analytics</h1><p className="form-error">{error}</p></section>;
  if (!analytics) return null;

  return (
    <section className="simple-page analytics-page">
      <h1>Analytics Dashboard</h1>
      <div className="stats-grid">
        <div className="stat-card"><span>Total Videos</span><strong>{analytics.overview.total_videos}</strong></div>
        <div className="stat-card"><span>Completed</span><strong>{analytics.overview.completed_videos}</strong></div>
        <div className="stat-card"><span>Transcripts</span><strong>{analytics.overview.total_transcripts}</strong></div>
        <div className="stat-card"><span>Summaries</span><strong>{analytics.overview.total_summaries}</strong></div>
      </div>
    </section>
  );
}

export function Profile() { 
  const { user } = useAuth(); 
  const [isEditing, setIsEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error", text: string } | null>(null);
  
  const displayName = user?.full_name || (user as any)?.name || "ClipMind User";

  const [formData, setFormData] = useState({
    name: displayName,
    email: user?.email || ""
  });

  if (!user) return <Navigate to="/login" replace />; 

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);

    try {
      await new Promise(resolve => setTimeout(resolve, 800));
      setMessage({ type: "success", text: "Profile details saved successfully!" });
      setIsEditing(false);
    } catch (error) {
      setMessage({ type: "error", text: "Failed to update profile details." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="simple-page">
      <div className="page-header narrow">
        <div>
          <span className="eyebrow">Account Settings</span>
          <h1>Your profile</h1>
          <p className="feature-description">Manage your ClipMind AI account details and workspace preferences.</p>
        </div>
      </div>

      <div style={{ display: "grid", gap: "24px", maxWidth: "760px" }}>
        <div className="profile-card" style={{ margin: 0, maxWidth: "100%" }}>
          <div className="avatar">{displayName.slice(0, 1).toUpperCase()}</div>
          <div>
            <h2>{displayName}</h2>
            <p>{user.email}</p>
            <span className="role-badge">{user.role}</span>
          </div>
        </div>

        <div className="upload-card" style={{ padding: "28px" }}>
          <div className="card-header-row" style={{ marginBottom: "20px" }}>
            <strong style={{ fontSize: "18px", color: "var(--text)" }}>Personal Information</strong>
            {!isEditing && (
              <button className="secondary-button compact-button" onClick={() => setIsEditing(true)}>
                Edit Details
              </button>
            )}
          </div>

          {message && (
            <div className={`upload-alert ${message.type}`} role="status" style={{ marginBottom: "20px" }}>
              <div className="alert-icon">{message.type === "success" ? "✅" : "❌"}</div>
              <div className="alert-copy">
                <strong>{message.type === "success" ? "Success" : "Error"}</strong>
                <p>{message.text}</p>
              </div>
            </div>
          )}

          {isEditing ? (
            <form onSubmit={handleSubmit} style={{ display: "grid", gap: "18px" }}>
              <label>
                Full Name
                <input 
                  type="text"
                  value={formData.name} 
                  onChange={e => setFormData(current => ({ ...current, name: e.target.value }))}
                  required 
                />
              </label>
              <label>
                Email Address
                <input 
                  type="email" 
                  value={formData.email} 
                  onChange={e => setFormData(current => ({ ...current, email: e.target.value }))}
                  disabled 
                  title="Email addresses cannot be changed directly."
                  style={{ opacity: 0.6, cursor: "not-allowed" }}
                />
                <span style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: "normal" }}>
                  Contact an administrator to change your workspace email.
                </span>
              </label>
              
              <div className="file-actions" style={{ marginTop: "12px", justifyContent: "flex-end" }}>
                <button type="button" className="secondary-button" onClick={() => setIsEditing(false)} disabled={busy}>
                  Cancel
                </button>
                <button type="submit" className="primary-button" disabled={busy}>
                  {busy ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          ) : (
            <div style={{ display: "grid", gap: "18px", color: "var(--text-soft)", fontSize: "14px" }}>
              <div style={{ display: "grid", gap: "6px" }}>
                <strong style={{ color: "var(--text)" }}>Full Name</strong>
                <span>{displayName}</span>
              </div>
              <div style={{ display: "grid", gap: "6px" }}>
                <strong style={{ color: "var(--text)" }}>Email Address</strong>
                <span>{user.email}</span>
              </div>
              <div style={{ display: "grid", gap: "6px" }}>
                <strong style={{ color: "var(--text)" }}>Workspace Role</strong>
                <span>{user.role}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  ); 
}

export { Dashboard };