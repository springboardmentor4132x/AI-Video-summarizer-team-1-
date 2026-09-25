import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { ArrowUpRight, BookOpen, Clapperboard, FileClock, FileText, Gauge, Library, MonitorCog, RefreshCw, ShieldCheck, Sparkles, Upload, Users, Video, WandSparkles } from "lucide-react";
import { useAuth } from "./features/auth/AuthContext";
import { TranscriptPanel } from "./features/transcripts/TranscriptPanel";
import {
  ApiError,
  checkPermission,
  getAdminAnalytics,
  getCreatorAnalytics,
  getTranscript,
  getUploadHistory,
  getVideoStatuses,
  getVideos,
  register as registerRequest,
  uploadVideo,
  type AnalyticsCountItem,
  type AnalyticsDashboard,
  type AnalyticsRange,
  type AnalyticsRangeKey,
  type AnalyticsRecentVideo,
  type Transcript,
  type VideoUploadResponse,
} from "./services/api";
import type { Role } from "./types/auth";

const dashboardConfig: Record<Role, { kicker: string; title: string; description: string; accent: string; actions: { label: string; detail: string; icon: typeof Video; route: string; endpoint?: string }[] }> = {
  "Content Creator": {
    kicker: "Creator studio", title: "Turn every upload into a sharper story.", description: "Your production desk for managing videos, monitoring processing, and keeping a clean publishing trail.", accent: "coral",
    actions: [
      { label: "Upload Video", detail: "Start a new media upload", icon: Video, route: "/creator/upload", endpoint: "/rbac/creator/uploads" },
      { label: "Manage Videos", detail: "Review your video library", icon: Library, route: "/creator/videos", endpoint: "/rbac/creator/uploads" },
      { label: "Transcriptions", detail: "Review transcript status and edit transcripts", icon: FileClock, route: "/creator/transcripts", endpoint: "/rbac/creator/uploads" },
      { label: "Upload History", detail: "Trace every file event", icon: FileClock, route: "/creator/history", endpoint: "/rbac/creator/history" },
      { label: "Processing Status", detail: "Watch jobs move forward", icon: Gauge, route: "/creator/processing", endpoint: "/rbac/creator/uploads" },
    ],
  },
  Learner: {
    kicker: "Learning space", title: "Find the signal inside the noise.", description: "A focused home for discovering available videos and returning to the content that matters.", accent: "mint",
    actions: [
      { label: "Available Videos", detail: "Browse the content library", icon: Video, route: "/learner/videos", endpoint: "/rbac/learner/content" },
      { label: "Learning Content", detail: "Open your learning shelf", icon: BookOpen, route: "/learner/content", endpoint: "/rbac/learner/content" },
      { label: "Summaries", detail: "Coming with AI processing", icon: WandSparkles, route: "/learner/summaries" },
      { label: "Transcriptions", detail: "Read generated transcripts", icon: FileClock, route: "/learner/transcripts" },
    ],
  },
  Educator: {
    kicker: "Teaching workspace", title: "Shape lectures into momentum.", description: "Prepare educational video content, keep classrooms organized, and see what is ready for learners.", accent: "gold",
    actions: [
      { label: "Upload Lecture", detail: "Add a new teaching video", icon: Video, route: "/educator/upload", endpoint: "/rbac/educator/content" },
      { label: "Manage Educational Content", detail: "Organize your teaching shelf", icon: Library, route: "/educator/content", endpoint: "/rbac/educator/content" },
      { label: "Transcriptions", detail: "Review and edit lecture transcripts", icon: FileClock, route: "/educator/transcripts", endpoint: "/rbac/educator/content" },
      { label: "Classroom Content", detail: "Keep lessons in one place", icon: BookOpen, route: "/educator/classroom", endpoint: "/rbac/educator/content" },
    ],
  },
  Administrator: {
    kicker: "Control room", title: "See the platform at a glance.", description: "A high-level operations view for people, permissions, activity, and system health.", accent: "blue",
    actions: [
      { label: "Users", detail: "Review platform accounts", icon: Users, route: "/admin/users", endpoint: "/rbac/admin/users" },
      { label: "Roles", detail: "Inspect access structure", icon: ShieldCheck, route: "/admin/roles", endpoint: "/rbac/admin/users" },
      { label: "Platform Activity", detail: "Follow recent events", icon: MonitorCog, route: "/admin/activity", endpoint: "/rbac/admin/platform" },
      { label: "System Monitoring", detail: "Check service readiness", icon: Gauge, route: "/admin/monitoring", endpoint: "/rbac/admin/platform" },
    ],
  },
};

function Dashboard() {
  const { user, token } = useAuth();
  const [notice, setNotice] = useState<string | null>(null);
  if (!user || !token) return <Navigate to="/login" replace />;
  const config = dashboardConfig[user.role];

  async function activate(label: string, endpoint?: string) {
    if (!endpoint) { setNotice(`${label} will arrive with the next ClipMind module.`); return; }
    if (!token) { setNotice("Please sign in again."); return; }
    const accessToken = token;
    try { const result = await checkPermission(endpoint, accessToken); setNotice(result.message); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Access check failed"); }
  }

  return <section className={`dashboard-page ${config.accent}`}>
    <header className="page-header"><div><span className="eyebrow">{config.kicker}</span><h1>{config.title}</h1><p>{config.description}</p></div><div className="status-pill"><span /> Workspace online</div></header>
    {notice && <div className="notice" role="status">{notice}</div>}
    <div className="stats-row"><div><span>ACCOUNT ROLE</span><strong>{user.role}</strong></div><div><span>ACCESS MODEL</span><strong>Role controlled</strong></div><div><span>AI OUTPUTS</span><strong>Module 2</strong></div></div>
    <div className="section-heading"><div><span className="eyebrow">Your command deck</span><h2>What would you like to do?</h2></div><span className="section-note">Backend authorization is always enforced</span></div>
    <div className="action-grid">{config.actions.map(({ label, detail, icon: Icon, route }) => <Link className="action-card" key={label} to={route}><span className="icon-tile"><Icon size={21} /></span><span className="card-copy"><strong>{label}</strong><small>{detail}</small></span><ArrowUpRight size={18} /></Link>)}</div>
  </section>;
}

export function RoleFeaturePage({ title, description, endpoint }: { title: string; description: string; endpoint?: string }) {
  const { token } = useAuth();
  const [status, setStatus] = useState("Checking access...");
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    if (!endpoint || !token) {
      setUnavailable(true);
      setStatus("This feature is not implemented yet.");
      return;
    }
    setUnavailable(false);
    checkPermission(endpoint, token)
      .then(result => setStatus(result.message))
      .catch(error => {
        if (error instanceof ApiError && error.status === 404) {
          setUnavailable(true);
          setStatus("This feature is not implemented yet.");
          return;
        }
        setStatus(error instanceof ApiError && error.status === 403
          ? "You do not have access to this feature."
          : "This feature could not be checked. Please try again later.");
      });
  }, [endpoint, token]);

  return <section className="simple-page feature-page"><span className="eyebrow">Role workspace</span><h1>{title}</h1><p className="feature-description">{description}</p><div className="feature-status" role="status"><span className="status-dot" />{status}</div><div className="feature-placeholder"><span className="eyebrow">{unavailable ? "Not implemented" : "Module ready"}</span><h2>Your {title.toLowerCase()} workspace</h2><p>{unavailable ? "This workspace feature is not currently available in ClipMind AI." : "Permissions are verified by the ClipMind API before this area can load content."}</p></div></section>;
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
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function validateFile(candidate: File) {
    const extension = `.${candidate.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!acceptedVideoTypes[extension] || candidate.type !== acceptedVideoTypes[extension]) return "Choose a supported video with a matching file type and extension.";
    if (candidate.size === 0) return "The selected video is empty.";
    if (candidate.size > maxVideoSizeBytes) return "The selected video exceeds the 500 MB limit.";
    return null;
  }

  function selectFile(candidate: File | undefined) {
    setMessage(null);
    const validationError = candidate ? validateFile(candidate) : null;
    setError(validationError);
    setFile(candidate && !validationError ? candidate : null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !token) { setError("Select a valid video before uploading."); return; }
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const result = await uploadVideo(token, file);
      setMessage(`${result.filename} uploaded successfully. Processing status: ${result.status}.`);
      setFile(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The video could not be uploaded.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="simple-page upload-page"><span className="eyebrow">Video intake</span><h1>Upload a video</h1><p className="feature-description">Add a source video to your ClipMind workspace. AI transcription and summarization are not started by this upload.</p><form className="upload-form" onSubmit={submit}><label htmlFor="video-file">Video file<input id="video-file" type="file" accept={Object.keys(acceptedVideoTypes).join(",")} onChange={event => selectFile(event.target.files?.[0])} /></label>{file && <div className="selected-file"><strong>{file.name}</strong><span>{(file.size / (1024 * 1024)).toFixed(2)} MB</span></div>}{error && <p className="form-error" role="alert">{error}</p>}{message && <p className="upload-success" role="status">{message}</p>}<button className="primary-button" disabled={busy || !file}>{busy ? "Uploading..." : "Upload video"}</button></form></section>;
}

export function UploadHistoryPage({ administrator = false }: { administrator?: boolean }) {
  const { token } = useAuth();
  const [events, setEvents] = useState<VideoUploadResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    getUploadHistory(token, administrator)
      .then(setEvents)
      .catch(reason => setError(reason instanceof Error ? reason.message : "Upload history could not be loaded."))
      .finally(() => setLoading(false));
  }, [administrator, token]);

  return <section className="simple-page history-page"><span className="eyebrow">{administrator ? "Platform activity" : "Creator studio"}</span><h1>{administrator ? "Upload activity" : "Upload history"}</h1><p className="feature-description">{administrator ? "Monitor upload and processing events across the ClipMind platform." : "Review the upload and processing events for your videos."}</p>{loading && <div className="feature-status" role="status"><span className="status-dot" />Loading upload history...</div>}{error && <div className="notice" role="alert">{error}</div>}{!loading && !error && events.length === 0 && <div className="feature-placeholder"><span className="eyebrow">No events yet</span><h2>Your upload history is empty</h2><p>Accepted uploads and future processing events will appear here.</p></div>}{!loading && !error && events.length > 0 && <div className="history-table-wrap"><table className="history-table"><thead><tr><th>Video</th><th>Status</th><th>Uploaded</th></tr></thead><tbody>{events.map(event => <tr key={event.id}><td><strong>{event.filename}</strong><small>{event.id}</small></td><td><span className={`event-status ${event.status.toLowerCase()}`}>{event.status}</span></td><td>{new Date(event.uploaded_at).toLocaleString()}</td></tr>)}</tbody></table></div>}</section>;
}

export function ProcessingStatusPage() {
  const { token } = useAuth();
  const [videos, setVideos] = useState<VideoUploadResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    getVideoStatuses(token)
      .then(setVideos)
      .catch(reason => setError(reason instanceof Error ? reason.message : "Processing status could not be loaded."))
      .finally(() => setLoading(false));
  }, [token]);

  return <section className="simple-page status-page"><span className="eyebrow">Creator studio</span><h1>Processing status</h1><p className="feature-description">Track the current lifecycle state of your uploaded videos. AI processing is not started by this view.</p>{loading && <div className="feature-status" role="status"><span className="status-dot" />Loading current statuses...</div>}{error && <div className="notice" role="alert">{error}</div>}{!loading && !error && videos.length === 0 && <div className="feature-placeholder"><span className="eyebrow">Nothing processing</span><h2>No uploaded videos yet</h2><p>Upload a video to begin tracking its lifecycle.</p></div>}{!loading && !error && videos.length > 0 && <div className="status-list">{videos.map(video => <article className="status-card" key={video.id}><div><strong>{video.filename}</strong><small>Uploaded {new Date(video.uploaded_at).toLocaleString()}</small></div><span className={`event-status ${video.status.toLowerCase()}`}>{video.status}</span></article>)}</div>}</section>;
}

export function VideoLibraryPage({ heading, description }: { heading: string; description: string }) {
  const { token, user } = useAuth();
  const [videos, setVideos] = useState<VideoUploadResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const rolePrefix: string | null = user
    ? { "Content Creator": "/creator", Learner: "/learner", Educator: "/educator", Administrator: null }[user.role] ?? null
    : null;

  async function loadVideos() {
    if (!token) return;
    setLoading(true);
    setError(null);
    try { setVideos(await getVideos(token)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Videos could not be loaded."); }
    finally { setLoading(false); }
  }

  useEffect(() => { void loadVideos(); }, [token]);

  const detailHref = (id: number) => `${rolePrefix}/videos/${id}`;


  return <section className="simple-page library-page"><span className="eyebrow">Video library</span><h1>{heading}</h1><p className="feature-description">{description}</p>{loading && <div className="feature-status" role="status"><span className="status-dot" />Loading videos...</div>}{error && <div className="notice" role="alert">{error}<button className="text-button" onClick={() => void loadVideos()}>Try again</button></div>}{!loading && !error && videos.length === 0 && <div className="feature-placeholder"><span className="eyebrow">No videos available</span><h2>Your library is empty</h2><p>Uploaded videos will appear here with their processing status.</p></div>}{!loading && !error && videos.length > 0 && <div className="video-grid">{videos.map(video => <article className="video-card" key={video.id}><div className="video-card-top"><Video size={20} /><span className={`event-status ${video.status.toLowerCase()}`}>{video.status}</span></div><h2>{video.filename}</h2><small>Uploaded {new Date(video.uploaded_at).toLocaleString()}</small>{rolePrefix && <Link className="auth-link" to={detailHref(video.id)} state={{ video }}>Open video details</Link>}</article>)}</div>}</section>;
}

export function TranscriptLibraryPage({ heading, description }: { heading: string; description: string }) {
  const { token, user } = useAuth();
  const [videos, setVideos] = useState<VideoUploadResponse[]>([]);
  const [transcripts, setTranscripts] = useState<Record<number, Transcript | null>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const rolePrefix = user ? { "Content Creator": "/creator", Learner: "/learner", Educator: "/educator", Administrator: null }[user.role] ?? null : null;

  useEffect(() => {
    let active = true;
    if (!token) { setLoading(false); return; }
    setLoading(true); setError(null);
    getVideos(token).then(async items => {
      if (!active) return;
      setVideos(items);
      const pairs = await Promise.all(items.map(async video => {
        try {
          const transcript = await getTranscript(token, video.id);
          return [video.id, transcript.video_id === video.id ? transcript : null] as const;
        } catch (reason) {
          if (reason instanceof ApiError && reason.status === 404) return [video.id, null] as const;
          throw reason;
        }
      }));
      if (active) setTranscripts(Object.fromEntries(pairs));
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "Transcripts could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token]);

  return <section className="simple-page library-page transcript-library"><span className="eyebrow">Transcript management</span><h1>{heading}</h1><p className="feature-description">{description}</p>
    {loading && <div className="feature-status" role="status"><span className="status-dot" />Loading transcript statuses...</div>}
    {error && <div className="notice" role="alert">{error}</div>}
    {!loading && !error && videos.length === 0 && <div className="feature-placeholder"><span className="eyebrow">No videos available</span><h2>No transcripts to review</h2><p>Videos available to your account will appear here.</p></div>}
    {!loading && !error && videos.length > 0 && <div className="history-table-wrap"><table className="history-table"><thead><tr><th>Video</th><th>Transcript status</th><th>Availability</th><th>Updated</th><th>Action</th></tr></thead><tbody>{videos.map(video => {
      const transcript = transcripts[video.id];
      const status = transcript?.status ?? "NOT_STARTED";
      const availability = status === "COMPLETED" && (transcript?.segments?.length || transcript?.text?.trim()) ? "Available" : status === "COMPLETED" ? "No transcript text" : "Unavailable";
      return <tr key={video.id}><td><strong>{video.filename}</strong></td><td><span className={`event-status ${status.toLowerCase()}`}>{status}</span></td><td>{availability}</td><td>{transcript ? new Date(transcript.updated_at).toLocaleString() : "—"}</td><td>{rolePrefix && <Link className="text-button" to={`${rolePrefix}/transcripts/${video.id}`}>{status === "PROCESSING" || status === "PENDING" ? "View Status" : "View Transcript"}</Link>}</td></tr>;
    })}</tbody></table></div>}
  </section>;
}

export function VideoDetailsPage({ transcriptOnly = false }: { transcriptOnly?: boolean }) {
  const { videoId } = useParams();
  const { token, user } = useAuth();
  const [video, setVideo] = useState<VideoUploadResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const rolePrefix = user ? { "Content Creator": "/creator", Learner: "/learner", Educator: "/educator", Administrator: null }[user.role] ?? null : null;
  useEffect(() => {
    let active = true;
    if (!token || !videoId) { setLoading(false); return; }
    setLoading(true); setError(null); setVideo(null);
    getVideos(token).then(items => {
      if (!active) return;
      const selected = items.find(item => item.id === Number(videoId));
      if (!selected) setError("This video is not available to your account.");
      else setVideo(selected);
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "Video details could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, videoId]);
  if (loading) return <section className="simple-page"><div className="feature-status" role="status"><span className="status-dot" />Loading video...</div></section>;
  if (error || !video || !videoId) return <section className="simple-page"><div className="notice" role="alert">{error ?? "Video not found."}</div></section>;
  return <section className="simple-page"><Link className="auth-link" to={transcriptOnly ? `${rolePrefix}/transcripts` : `${rolePrefix}/videos`}>← Back to {transcriptOnly ? "Transcriptions" : "Videos"}</Link><TranscriptPanel videoId={video.id} filename={video.filename} transcriptOnly={transcriptOnly} transcriptHref={rolePrefix ? `${rolePrefix}/transcripts/${video.id}` : undefined} /></section>;
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
  return <main className="login-page"><div className="login-art"><div className="brand"><span className="brand-mark">C</span><span>ClipMind <em>AI</em></span></div><div className="art-copy"><span className="eyebrow">Intelligence for every frame</span><h1>Make the important moments easier to find.</h1><p>One calm workspace for creators, learners, educators, and the people keeping it all running.</p></div><div className="orbit-card"><Clapperboard size={19} /><span>Video intelligence platform</span></div></div><div className="login-panel"><div className="form-wrap"><span className="eyebrow">Welcome back</span><h2>Sign in to ClipMind</h2><p className="form-intro">Use your account credentials to open your role workspace.</p><form onSubmit={submit}><label>Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} required /></label><label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required /></label>{error && <p className="form-error">{error}</p>}<button className="primary-button" disabled={busy}>{busy ? "Signing in..." : "Continue to workspace"}</button></form><Link className="auth-link" to="/register">Create an account</Link></div></div></main>;
}

export function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", confirm_password: "", role: "Learner" });
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
    try { await registerRequest(form); setSuccess("Account created. Redirecting to sign in..."); setTimeout(() => navigate("/login"), 700); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Registration failed."); }
    finally { setBusy(false); }
  }
  return <main className="login-page"><div className="login-art"><div className="brand"><span className="brand-mark">C</span><span>ClipMind <em>AI</em></span></div><div className="art-copy"><span className="eyebrow">Start your workspace</span><h1>Give every frame somewhere useful to go.</h1><p>Create a role-aware ClipMind account for making, learning, or teaching.</p></div></div><div className="login-panel"><div className="form-wrap"><span className="eyebrow">New account</span><h2>Join ClipMind</h2><p className="form-intro">Your role determines the workspace and permissions you receive.</p><form onSubmit={submit}><label>Full name<input value={form.full_name} onChange={event => update("full_name", event.target.value)} required /></label><label>Email<input type="email" value={form.email} onChange={event => update("email", event.target.value)} required /></label><label>Role<select value={form.role} onChange={event => update("role", event.target.value)}><option>Content Creator</option><option>Learner</option><option>Educator</option></select></label><label>Password<input type="password" value={form.password} onChange={event => update("password", event.target.value)} minLength={8} required /></label><label>Confirm password<input type="password" value={form.confirm_password} onChange={event => update("confirm_password", event.target.value)} minLength={8} required /></label>{error && <p className="form-error" role="alert">{error}</p>}{success && <p className="upload-success" role="status">{success}</p>}<button className="primary-button" disabled={busy}>{busy ? "Creating account..." : "Create account"}</button></form><Link className="auth-link" to="/login">Back to sign in</Link></div></div></main>;
}

export function Profile() { const { user } = useAuth(); if (!user) return <Navigate to="/login" replace />; return <section className="simple-page"><span className="eyebrow">Account</span><h1>Your profile</h1><div className="profile-card"><div className="avatar">{user.name.slice(0, 1)}</div><div><h2>{user.name}</h2><p>{user.email}</p><span className="role-badge">{user.role}</span></div></div></section>; }

function rangeFor(key: AnalyticsRangeKey): AnalyticsRange {
  if (key === "all") return {};
  const days = key === "7d" ? 7 : key === "30d" ? 30 : 90;
  const now = new Date();
  const past = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
  return {
    from: past.toISOString().slice(0, 10),
    to: now.toISOString().slice(0, 10),
  };
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatDuration(seconds: number | null) {
  if (seconds === null || seconds === undefined || seconds === 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

function V2Metric({ label, value, detail, icon: Icon, tone }: { label: string; value: string | number; detail: string; icon: typeof Video; tone: string }) {
  return (
    <article className={`analytics-metric-card ${tone}`}>
      <div className="metric-icon-wrap"><Icon size={20} /></div>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{typeof value === "number" ? value.toLocaleString() : value}</strong>
      <small className="metric-detail">{detail}</small>
    </article>
  );
}

function Pipeline({ analytics }: { analytics: AnalyticsDashboard }) {
  const stages = [
    { label: "Videos uploaded", count: analytics.processing_insights.videos.count, pct: analytics.processing_insights.videos.coverage_percentage },
    { label: "Transcripts generated", count: analytics.processing_insights.transcripts.count, pct: analytics.processing_insights.transcripts.coverage_percentage },
    { label: "Summaries created", count: analytics.processing_insights.summaries.count, pct: analytics.processing_insights.summaries.coverage_percentage },
    { label: "Key moments detected", count: analytics.processing_insights.key_moments.count, pct: analytics.processing_insights.key_moments.coverage_percentage },
  ];
  return (
    <div className="analytics-pipeline-grid">
      {stages.map(stage => (
        <div className="pipeline-stage-card" key={stage.label}>
          <span>{stage.label}</span>
          <strong>{stage.count}</strong>
          <small>{stage.pct}% completion</small>
          <div className="pipeline-bar"><em style={{ width: `${stage.pct}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

function LoadingAnalytics() {
  return (
    <section className="simple-page analytics-page">
      <div className="analytics-skeleton-head"><span /><span /><span /></div>
      <div className="analytics-skeleton-grid">
        {Array.from({ length: 4 }, (_, index) => (
          <div className="analytics-skeleton-card" key={index}><span /><strong /><small /></div>
        ))}
      </div>
      <div className="analytics-skeleton-panel" />
    </section>
  );
}

function Phase4VideoDetail({ video, onClose }: { video: AnalyticsRecentVideo; onClose: () => void }) {
  return (
    <div className="analytics-detail-backdrop" role="presentation" onClick={onClose}>
      <aside className="analytics-detail-panel" role="dialog" aria-modal="true" aria-label={`${video.filename} intelligence details`} onClick={event => event.stopPropagation()}>
        <button className="analytics-detail-close" type="button" aria-label="Close video details" onClick={onClose}>×</button>
        <span className="eyebrow">Video overview</span>
        <h2>{video.filename}</h2>
        <p>{video.status} · Uploaded {formatDate(video.uploaded_at)}</p>
        <div className="detail-score">
          <strong>{video.ai_score}</strong>
          <span>/ 100<br />AI content intelligence</span>
        </div>
        <div className="detail-breakdown">
          {Object.entries(video.ai_score_components).map(([label, score]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{Math.round(score)}%</strong>
              <i><em style={{ width: `${score}%` }} /></i>
            </div>
          ))}
        </div>
        <div className="detail-columns">
          <section>
            <span>Transcript</span>
            <strong>{video.transcript_status ?? "No transcript"}</strong>
            <small>{video.transcript_word_count.toLocaleString()} words · {video.transcript_character_count.toLocaleString()} chars</small>
          </section>
          <section>
            <span>Summary</span>
            <strong>{video.summary_status === "COMPLETED" ? "Generated" : video.summary_status ?? "Not generated"}</strong>
            <small>{video.summary_word_count.toLocaleString()} words</small>
          </section>
          <section>
            <span>Key moments</span>
            <strong>{video.key_moment_count}</strong>
            <small>{video.average_importance.toFixed(2)} average importance · {video.highest_importance.toFixed(2)} highest</small>
          </section>
          <section>
            <span>Content</span>
            <strong>{video.topic_count} topics</strong>
            <small>{video.top_keywords.join(", ") || "No keywords yet"}</small>
          </section>
        </div>
      </aside>
    </div>
  );
}

export function AnalyticsPage() {
  const { token, user } = useAuth();
  const [analytics, setAnalytics] = useState<AnalyticsDashboard | null>(null);
  const [rangeKey, setRangeKey] = useState<AnalyticsRangeKey>("all");
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedVideo, setSelectedVideo] = useState<AnalyticsRecentVideo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !user) return;
    let active = true;
    setLoading(true);
    setError(null);
    const loader = user.role === "Administrator" ? getAdminAnalytics : getCreatorAnalytics;
    loader(token, rangeFor(rangeKey))
      .then(result => { if (active) setAnalytics(result); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "Unable to load analytics."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, user, rangeKey, refreshKey]);

  if (loading && !analytics) return <LoadingAnalytics />;

  if (error) {
    return (
      <section className="simple-page analytics-page">
        <div className="analytics-error" role="alert">
          <span className="eyebrow">Analytics unavailable</span>
          <h1>Unable to load analytics</h1>
          <p>{error}</p>
          <button className="primary-button" type="button" onClick={() => setRefreshKey(value => value + 1)}>
            <RefreshCw size={16} /> Try again
          </button>
        </div>
      </section>
    );
  }

  if (!analytics) return null;

  const ranges: { key: AnalyticsRangeKey; label: string }[] = [
    { key: "7d", label: "7 Days" },
    { key: "30d", label: "30 Days" },
    { key: "90d", label: "90 Days" },
    { key: "all", label: "All Time" },
  ];

  const noVideos = analytics.overview.total_videos === 0;

  return (
    <section className="simple-page analytics-page">
      <header className="analytics-header">
        <div>
          <span className="eyebrow">ClipMind AI · Video intelligence center</span>
          <h1>Analytics</h1>
          <p>See what your videos contain, what the AI discovered, and what deserves attention next.</p>
        </div>
        <div className="analytics-actions">
          <div className="range-control" aria-label="Analytics date range">
            {ranges.map(range => (
              <button
                key={range.key}
                type="button"
                className={rangeKey === range.key ? "active" : ""}
                aria-pressed={rangeKey === range.key}
                onClick={() => setRangeKey(range.key)}
              >
                {range.label}
              </button>
            ))}
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="Refresh analytics"
            title="Refresh analytics"
            onClick={() => setRefreshKey(value => value + 1)}
            disabled={loading}
          >
            <RefreshCw size={16} className={loading ? "spin" : ""} />
          </button>
        </div>
      </header>

      {loading && (
        <div className="analytics-refreshing" role="status">
          <RefreshCw size={14} className="spin" /> Refreshing live data
        </div>
      )}

      {noVideos ? (
        <div className="analytics-empty-state">
          <span className="analytics-empty-icon"><Video size={25} /></span>
          <h2>No video analytics yet</h2>
          <p>Upload your first video to start generating transcripts, summaries, key moments, and insights.</p>
          <Link className="primary-button" to="/creator/upload"><Upload size={16} /> Upload Video</Link>
        </div>
      ) : (
        <>
          <div className="analytics-section-heading">
            <span className="eyebrow">Executive overview</span>
            <h2>AI content intelligence at a glance</h2>
          </div>
          <div className="analytics-metric-grid">
            <V2Metric label="Videos analyzed" value={analytics.overview.total_videos} detail={`${analytics.overview.completed_videos} completed`} icon={Clapperboard} tone="violet" />
            <V2Metric label="Transcripts" value={analytics.overview.total_transcripts} detail={`${analytics.transcript_insights.total_words.toLocaleString()} words`} icon={FileText} tone="cyan" />
            <V2Metric label="AI summaries" value={analytics.summary_insights.completed_summaries} detail={`${analytics.summary_insights.generation_rate_percentage}% coverage`} icon={Sparkles} tone="amber" />
            <V2Metric label="Key moments" value={analytics.overview.total_key_moments} detail={`${analytics.key_moment_insights.videos_with_key_moments} videos surfaced`} icon={WandSparkles} tone="rose" />
            <article className="intelligence-score-card">
              <span className="eyebrow">AI content intelligence</span>
              <strong>{analytics.intelligence_score.score}</strong>
              <span>/ 100</span>
              <p>{analytics.intelligence_score.explanation}</p>
            </article>
          </div>

          <div className="analytics-phase4-grid">
            <article className="analytics-panel analytics-phase4-wide">
              <div className="section-heading">
                <div><span className="eyebrow">AI insights</span><h2>What deserves attention</h2></div>
              </div>
              <div className="ai-insights-grid">
                {analytics.ai_insights.length ? (
                  analytics.ai_insights.map(insight => (
                    <div className={`ai-insight ${insight.category.toLowerCase().replace(" ", "-")}`} key={`${insight.category}-${insight.title}`}>
                      <span>{insight.category}</span>
                      <strong>{insight.title}</strong>
                      <p>{insight.message}</p>
                      {insight.metric && <em>{insight.metric}</em>}
                    </div>
                  ))
                ) : (
                  <div className="analytics-empty-block">More content is needed to generate data-driven insights.</div>
                )}
              </div>
            </article>

            <article className="analytics-panel">
              <div className="section-heading">
                <div><span className="eyebrow">Topic intelligence</span><h2>Top content topics</h2></div>
              </div>
              <div className="topic-list">
                {analytics.top_topics.map(topic => (
                  <button type="button" key={topic.topic} onClick={() => setSelectedVideo(null)}>
                    <span><strong>{topic.topic}</strong><small>{topic.video_count} videos · {topic.frequency} occurrences</small></span>
                    <b>{topic.percentage}%</b>
                  </button>
                ))}
              </div>
            </article>

            <article className="analytics-panel">
              <div className="section-heading">
                <div><span className="eyebrow">Advanced keywords</span><h2>Keyword intelligence</h2></div>
              </div>
              <div className="keyword-list">
                {analytics.keyword_intelligence.slice(0, 8).map(keyword => (
                  <div key={keyword.keyword}>
                    <span><strong>{keyword.keyword}</strong><small>{keyword.frequency} occurrences · {keyword.video_count} videos</small></span>
                    <b>{keyword.share_percentage}%</b>
                  </div>
                ))}
              </div>
            </article>

            <article className="analytics-panel analytics-phase4-wide">
              <div className="section-heading">
                <div><span className="eyebrow">Video intelligence</span><h2>Compare your content</h2></div>
                <span className="section-note">Select a row for details</span>
              </div>
              <div className="video-intelligence-table-wrap">
                <table className="video-intelligence-table">
                  <thead>
                    <tr>
                      <th>Video</th>
                      <th>Duration</th>
                      <th>Words</th>
                      <th>Topics</th>
                      <th>Summary</th>
                      <th>Moments</th>
                      <th>AI score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analytics.recent_videos.map(video => (
                      <tr
                        key={video.id}
                        onClick={() => setSelectedVideo(video)}
                        tabIndex={0}
                        onKeyDown={event => { if (event.key === "Enter") setSelectedVideo(video); }}
                      >
                        <td><strong>{video.filename}</strong><small>{video.status} · {formatDate(video.uploaded_at)}</small></td>
                        <td>{formatDuration(video.duration_seconds)}</td>
                        <td>{video.transcript_status ? video.transcript_word_count.toLocaleString() : "No transcript"}</td>
                        <td>{video.topic_count}</td>
                        <td>{video.summary_status === "COMPLETED" ? "Ready" : "Not generated"}</td>
                        <td>{video.key_moment_count}</td>
                        <td><b className="score-pill">{video.ai_score}</b></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </div>

          <article className="analytics-panel analytics-phase4-wide">
            <div className="section-heading">
              <div><span className="eyebrow">Pipeline detail</span><h2>From video to understanding</h2></div>
            </div>
            <Pipeline analytics={analytics} />
          </article>
        </>
      )}

      {selectedVideo && <Phase4VideoDetail video={selectedVideo} onClose={() => setSelectedVideo(null)} />}
    </section>
  );
}

export { Dashboard };
