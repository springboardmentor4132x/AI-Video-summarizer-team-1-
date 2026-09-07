import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ArrowUpRight, BookOpen, Clapperboard, FileClock, Gauge, Library, MonitorCog, ShieldCheck, Users, Video, WandSparkles } from "lucide-react";
import { useAuth } from "./features/auth/AuthContext";
import { TranscriptPanel } from "./features/transcripts/TranscriptPanel";
import { checkPermission, getUploadHistory, getVideoStatuses, getVideos, register as registerRequest, uploadVideo, type UploadHistoryEvent, type VideoListItem, type VideoStatus } from "./services/api";
import type { Role } from "./types/auth";

const dashboardConfig: Record<Role, { kicker: string; title: string; description: string; accent: string; actions: { label: string; detail: string; icon: typeof Video; route: string; endpoint?: string }[] }> = {
  "Content Creator": {
    kicker: "Creator studio", title: "Turn every upload into a sharper story.", description: "Your production desk for managing videos, monitoring processing, and keeping a clean publishing trail.", accent: "coral",
    actions: [
      { label: "Upload Video", detail: "Start a new media upload", icon: Video, route: "/creator/upload", endpoint: "/rbac/creator/uploads" },
      { label: "Manage Videos", detail: "Review your video library", icon: Library, route: "/creator/videos", endpoint: "/rbac/creator/uploads" },
      { label: "Transcripts", detail: "Generate and edit transcripts", icon: FileClock, route: "/creator/transcripts", endpoint: "/rbac/creator/uploads" },
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
      { label: "Transcripts", detail: "Read generated transcripts", icon: FileClock, route: "/learner/transcripts" },
    ],
  },
  Educator: {
    kicker: "Teaching workspace", title: "Shape lectures into momentum.", description: "Prepare educational video content, keep classrooms organized, and see what is ready for learners.", accent: "gold",
    actions: [
      { label: "Upload Lecture", detail: "Add a new teaching video", icon: Video, route: "/educator/upload", endpoint: "/rbac/educator/content" },
      { label: "Manage Educational Content", detail: "Organize your teaching shelf", icon: Library, route: "/educator/content", endpoint: "/rbac/educator/content" },
      { label: "Transcripts", detail: "Generate and edit lecture transcripts", icon: FileClock, route: "/educator/transcripts", endpoint: "/rbac/educator/content" },
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

  useEffect(() => {
    if (!endpoint || !token) {
      setStatus("This workspace is ready for the next content module.");
      return;
    }
    checkPermission(endpoint, token)
      .then(result => setStatus(result.message))
      .catch(error => setStatus(error instanceof Error ? error.message : "Access check failed"));
  }, [endpoint, token]);

  return <section className="simple-page feature-page"><span className="eyebrow">Role workspace</span><h1>{title}</h1><p className="feature-description">{description}</p><div className="feature-status" role="status"><span className="status-dot" />{status}</div><div className="feature-placeholder"><span className="eyebrow">Module ready</span><h2>Your {title.toLowerCase()} workspace</h2><p>Permissions are verified by the ClipMind API before this area can load content.</p></div></section>;
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
      setMessage(`${result.filename} uploaded successfully. Processing status: ${result.processing_status}.`);
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
  const [events, setEvents] = useState<UploadHistoryEvent[]>([]);
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

  return <section className="simple-page history-page"><span className="eyebrow">{administrator ? "Platform activity" : "Creator studio"}</span><h1>{administrator ? "Upload activity" : "Upload history"}</h1><p className="feature-description">{administrator ? "Monitor upload and processing events across the ClipMind platform." : "Review the upload and processing events for your videos."}</p>{loading && <div className="feature-status" role="status"><span className="status-dot" />Loading upload history...</div>}{error && <div className="notice" role="alert">{error}</div>}{!loading && !error && events.length === 0 && <div className="feature-placeholder"><span className="eyebrow">No events yet</span><h2>Your upload history is empty</h2><p>Accepted uploads and future processing events will appear here.</p></div>}{!loading && !error && events.length > 0 && <div className="history-table-wrap"><table className="history-table"><thead><tr><th>Video</th>{administrator && <th>Owner</th>}<th>Status</th><th>Timestamp</th><th>Event notes</th></tr></thead><tbody>{events.map(event => <tr key={event.id}><td><strong>{event.filename}</strong><small>{event.video_id}</small></td>{administrator && <td>{event.owner_name}</td>}<td><span className={`event-status ${event.status.toLowerCase()}`}>{event.status}</span></td><td>{new Date(event.timestamp).toLocaleString()}</td><td>{event.notes ?? "-"}</td></tr>)}</tbody></table></div>}</section>;
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

  return <section className="simple-page status-page"><span className="eyebrow">Creator studio</span><h1>Processing status</h1><p className="feature-description">Track the current lifecycle state of your uploaded videos. AI processing is not started by this view.</p>{loading && <div className="feature-status" role="status"><span className="status-dot" />Loading current statuses...</div>}{error && <div className="notice" role="alert">{error}</div>}{!loading && !error && videos.length === 0 && <div className="feature-placeholder"><span className="eyebrow">Nothing processing</span><h2>No uploaded videos yet</h2><p>Upload a video to begin tracking its lifecycle.</p></div>}{!loading && !error && videos.length > 0 && <div className="status-list">{videos.map(video => <article className="status-card" key={video.id}><div><strong>{video.filename}</strong><small>Updated {new Date(video.updated_at).toLocaleString()}</small></div><span className={`event-status ${video.processing_status.toLowerCase()}`}>{video.processing_status}</span><p>{video.latest_note ?? "No status notes yet."}</p></article>)}</div>}</section>;
}

export function VideoLibraryPage({ heading, description }: { heading: string; description: string }) {
  const { token, user } = useAuth();
  const [videos, setVideos] = useState<VideoListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadVideos() {
    if (!token) return;
    setLoading(true);
    setError(null);
    try { setVideos(await getVideos(token)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Videos could not be loaded."); }
    finally { setLoading(false); }
  }

  useEffect(() => { void loadVideos(); }, [token]);

   return <section className="simple-page library-page"><span className="eyebrow">Video library</span><h1>{heading}</h1><p className="feature-description">{description}</p>{loading && <div className="feature-status" role="status"><span className="status-dot" />Loading videos...</div>}{error && <div className="notice" role="alert">{error}<button className="text-button" onClick={() => void loadVideos()}>Try again</button></div>}{!loading && !error && videos.length === 0 && <div className="feature-placeholder"><span className="eyebrow">No videos available</span><h2>Your library is empty</h2><p>Uploaded videos will appear here with their processing status.</p></div>}{!loading && !error && videos.length > 0 && <div className="video-grid">{videos.map(video => <article className="video-card" key={video.id}><div className="video-card-top"><Video size={20} /><span className={`event-status ${video.processing_status.toLowerCase()}`}>{video.processing_status}</span></div><h2>{video.filename}</h2><p>{video.owner_name} · {(video.file_size_bytes / (1024 * 1024)).toFixed(2)} MB</p><small>{video.duration_seconds ? `${video.duration_seconds}s` : "Duration pending"} · Uploaded {new Date(video.uploaded_at).toLocaleDateString()}</small>{user && <TranscriptPanel videoId={video.id} ownerId={video.owner_id} filename={video.filename} />}</article>)}</div>}</section>;
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
  return <main className="login-page"><div className="login-art"><div className="brand"><span className="brand-mark">C</span><span>ClipMind <em>AI</em></span></div><div className="art-copy"><span className="eyebrow">Start your workspace</span><h1>Give every frame somewhere useful to go.</h1><p>Create a role-aware ClipMind account for making, learning, teaching, or operating.</p></div></div><div className="login-panel"><div className="form-wrap"><span className="eyebrow">New account</span><h2>Join ClipMind</h2><p className="form-intro">Your role determines the workspace and permissions you receive.</p><form onSubmit={submit}><label>Full name<input value={form.full_name} onChange={event => update("full_name", event.target.value)} required /></label><label>Email<input type="email" value={form.email} onChange={event => update("email", event.target.value)} required /></label><label>Role<select value={form.role} onChange={event => update("role", event.target.value)}><option>Content Creator</option><option>Learner</option><option>Educator</option><option>Administrator</option></select></label><label>Password<input type="password" value={form.password} onChange={event => update("password", event.target.value)} minLength={8} required /></label><label>Confirm password<input type="password" value={form.confirm_password} onChange={event => update("confirm_password", event.target.value)} minLength={8} required /></label>{error && <p className="form-error" role="alert">{error}</p>}{success && <p className="upload-success" role="status">{success}</p>}<button className="primary-button" disabled={busy}>{busy ? "Creating account..." : "Create account"}</button></form><Link className="auth-link" to="/login">Back to sign in</Link></div></div></main>;
}

export function Profile() { const { user } = useAuth(); if (!user) return <Navigate to="/login" replace />; return <section className="simple-page"><span className="eyebrow">Account</span><h1>Your profile</h1><div className="profile-card"><div className="avatar">{user.full_name.slice(0, 1)}</div><div><h2>{user.full_name}</h2><p>{user.email}</p><span className="role-badge">{user.role}</span></div></div></section>; }

export { Dashboard };
