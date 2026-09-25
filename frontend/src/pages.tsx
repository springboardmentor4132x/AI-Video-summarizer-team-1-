import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { Activity, ArrowUpRight, BookOpen, CalendarDays, Clapperboard, Clock3, FileClock, Gauge, HardDrive, MonitorCog, RefreshCw, Search, ShieldCheck, Trash2, User, Users, Video, WandSparkles, Sparkles, Upload, Download, FileText, CircleCheckBig, ClapperboardIcon, ArrowRight, CirclePlay } from "lucide-react";
import { withApiBase } from "./config";
import { Modal } from "./components/Modal";
import { useAuth } from "./features/auth/AuthContext";
import { ApiError, checkPermission, deleteVideo, downloadTranscript, generateKeyMoments, generateSummary, generateTranscript, getAdminAnalytics, getCreatorAnalytics, getKeyMoments, getSummary, getTranscript, getUploadHistory, getVideoStatuses, getVideos, getVideoMediaUrl, register as registerRequest, retrySummary, uploadVideo, type AnalyticsDashboard, type AnalyticsRange, type AnalyticsRecentVideo, type KeyMoment, type Summary, type Transcript, type UploadHistoryEvent, type VideoListItem, type VideoStatus } from "./services/api";
import type { Role } from "./types/auth";

const dashboardConfig: Record<Role, { kicker: string; title: string; description: string; accent: string; actions: { label: string; detail: string; icon: typeof Video; route: string; endpoint?: string }[] }> = {
  "Content Creator": {
    kicker: "Creator studio", title: "Turn long videos into useful knowledge.", description: "Upload content, review transcripts, summarize key ideas, and keep the full workflow moving from one place.", accent: "coral",
    actions: [
      { label: "Upload Video", detail: "Start a new media upload", icon: Video, route: "/creator/upload", endpoint: "/rbac/creator/uploads" },
      { label: "Transcripts", detail: "Generate and edit transcripts", icon: FileClock, route: "/creator/transcripts", endpoint: "/rbac/creator/uploads" },
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

function getTranscriptStateMessage(state: ReturnType<typeof getTranscriptState>) {
  switch (state) {
    case "processing":
      return "🎙️ Processing transcript...";
    case "transcript_ready":
      return "🟢 Transcript ready";
    case "transcript_failed":
      return "⚠️ Transcript generation failed";
    case "transcript_missing":
    default:
      return "📝 Transcript isn't available yet.";
  }
}

function Dashboard() {
  const { user, token } = useAuth();
  const [notice, setNotice] = useState<string | null>(null);
  const [stats, setStats] = useState<{ videos: number | null; transcripts: number | null; summaries: number | null; keyMoments: number | null; }>({ videos: null, transcripts: null, summaries: null, keyMoments: null });

  useEffect(() => {
    async function loadData() {
      if (!user || !token) return;

      try {
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
        setStats({ videos: null, transcripts: null, summaries: null, keyMoments: null });
      }
    }

    void loadData();
  }, [token, user, user?.role]);

  async function activate(label: string, endpoint?: string) {
    if (!endpoint) { setNotice(`${label} will arrive with the next ClipMind module.`); return; }
    if (!token) { setNotice("Please sign in again."); return; }
    const accessToken = token;
    try { const result = await checkPermission(endpoint, accessToken); setNotice(result.message); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Access check failed"); }
  }

  if (!user || !token) return <Navigate to="/login" replace />;

  const config = dashboardConfig[user.role];
  const statCards = [
    { label: "Videos", value: stats.videos ?? 0, tone: "teal", icon: Clapperboard },
    { label: "Transcripts", value: stats.transcripts ?? 0, tone: "amber", icon: FileText },
    { label: "AI Summaries", value: stats.summaries ?? 0, tone: "rose", icon: Sparkles },
    { label: "Key Moments", value: stats.keyMoments ?? 0, tone: "slate", icon: WandSparkles },
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

function AnalyticsBars({ items, emptyMessage }: { items: { label: string; count: number }[]; emptyMessage: string }) {
  const maximum = Math.max(...items.map(item => item.count), 1);
  if (!items.length) return <p className="analytics-empty">{emptyMessage}</p>;
  return <div className="analytics-bars">{items.map(item => <div className="analytics-bar" key={item.label}><div><span>{item.label}</span><strong>{item.count}</strong></div><span className="analytics-bar-track"><i style={{ width: `${Math.max((item.count / maximum) * 100, 2)}%` }} /></span></div>)}</div>;
}

function ActivityChart({ items }: { items: { date: string; count: number }[] }) {
  const maximum = Math.max(...items.map(item => item.count), 1);
  if (!items.length) return <p className="analytics-empty">No activity recorded yet.</p>;
  return <div className="analytics-activity-chart" aria-label="Upload activity over time">{items.slice(-14).map(item => <div className="analytics-activity-column" key={item.date}><strong>{item.count}</strong><span><i style={{ height: `${Math.max((item.count / maximum) * 100, 3)}%` }} /></span><small>{item.date.slice(5)}</small></div>)}</div>;
}

function AnalyticsMetric({ label, value, tone = "teal" }: { label: string; value: string | number; tone?: string }) {
  return <div className={`stat-card ${tone}`}><div className="stat-header"><span>{label}</span></div><strong>{value}</strong></div>;
}

function LegacyAnalyticsPage() {
  const { token, user } = useAuth();
  const [analytics, setAnalytics] = useState<AnalyticsDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    const loadAnalytics = user?.role === "Administrator" ? getAdminAnalytics : getCreatorAnalytics;
    loadAnalytics(token)
      .then(setAnalytics)
      .catch(reason => setError(reason instanceof Error ? reason.message : "Analytics could not be loaded."))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) return <section className="simple-page analytics-page"><span className="eyebrow">Platform intelligence</span><h1>Analytics Dashboard</h1><div className="feature-status" role="status">Loading analytics...</div></section>;
  if (error) return <section className="simple-page analytics-page"><span className="eyebrow">Platform intelligence</span><h1>Analytics Dashboard</h1><div className="notice" role="alert">{error}</div></section>;
  if (!analytics) return <section className="simple-page analytics-page"><span className="eyebrow">Platform intelligence</span><h1>Analytics Dashboard</h1><div className="feature-placeholder"><h2>No analytics data available yet.</h2><p>There is no stored platform activity to summarize.</p></div></section>;

  const { overview, video_analytics: video, summary_reports: summaries, content_insights: content, key_moment_analytics: moments, usage } = analytics;
  return <section className="simple-page analytics-page"><header className="page-header"><div><span className="eyebrow">Platform intelligence</span><h1>Analytics Dashboard</h1><p>Understand platform activity and the content flowing through ClipMind AI.</p></div><div className="status-pill"><span className="status-dot" /> Live database data</div></header><div className="stats-grid analytics-stats"><AnalyticsMetric label="Total Videos" value={overview.total_videos} /><AnalyticsMetric label="Completed" value={overview.completed_videos} tone="teal" /><AnalyticsMetric label="Total Duration" value={formatDuration(overview.total_duration_seconds)} tone="amber" /><AnalyticsMetric label="Key Moments" value={overview.total_key_moments} tone="rose" /><AnalyticsMetric label="Summaries" value={overview.total_summaries} tone="slate" /><AnalyticsMetric label="Transcripts" value={overview.total_transcripts} tone="teal" /><AnalyticsMetric label="Users" value={overview.total_users} tone="amber" /><AnalyticsMetric label="Failed Processing" value={overview.failed_videos} tone="rose" /></div><div className="analytics-grid"><article className="analytics-panel analytics-wide"><div className="section-heading"><div><span className="eyebrow">Video analytics</span><h2>Upload activity</h2></div><span className="section-note">{overview.processing_videos} in progress</span></div><ActivityChart items={video.upload_activity} /></article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Processing</span><h2>Status distribution</h2></div></div><AnalyticsBars items={video.status_distribution} emptyMessage="No videos have been uploaded yet." /></article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Summary reports</span><h2>Generation rate</h2></div></div><div className="analytics-highlight"><strong>{summaries.generation_rate_percentage}%</strong><span>{summaries.completed_summaries} completed summaries across {summaries.videos_with_summaries} videos</span></div><div className="analytics-meta"><span>Summary text<strong>{summaries.total_summary_characters.toLocaleString()} characters</strong></span><span>Average video<strong>{formatDuration(overview.average_duration_seconds)}</strong></span></div></article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Content insights</span><h2>Frequent terms</h2></div></div><AnalyticsBars items={content.top_keywords.map(item => ({ label: item.keyword, count: item.count }))} emptyMessage="No transcript text is available yet." /><p className="analytics-note">Frequency from stored transcripts, excluding common words.</p></article><article className="analytics-panel analytics-wide"><div className="section-heading"><div><span className="eyebrow">Key moments</span><h2>Recent important moments</h2></div><span className="section-note">{moments.average_per_video} per video</span></div>{moments.recent_activity.length ? <div className="analytics-list">{moments.recent_activity.map(moment => <div className="analytics-list-row" key={moment.id}><div><strong>{moment.title}</strong><span>{moment.filename}{moment.topic ? ` · ${moment.topic}` : ""}</span></div><b>{moment.importance_score.toFixed(2)}</b></div>)}</div> : <p className="analytics-empty">No key moments have been detected yet.</p>}</article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Usage</span><h2>Users by role</h2></div></div><AnalyticsBars items={usage.users_by_role} emptyMessage="No users are available yet." /></article></div></section>;
}

type AnalyticsRangeKey = "7d" | "30d" | "90d" | "all";

function rangeFor(key: AnalyticsRangeKey): AnalyticsRange {
  if (key === "all") return {};
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - Number(key.replace("d", "")) + 1);
  const isoDate = (value: Date) => value.toISOString().slice(0, 10);
  return { from: isoDate(start), to: isoDate(end) };
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function V2Metric({ label, value, detail, icon: Icon, tone }: { label: string; value: string | number; detail: string; icon: typeof Video; tone: string }) {
  return <article className={`analytics-metric ${tone}`}><span className="analytics-metric-icon"><Icon size={18} /></span><span className="analytics-metric-label">{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function V2ActivityChart({ items }: { items: { date: string; count: number }[] }) {
  if (!items.length) return <div className="analytics-empty-block">No video activity in this range.</div>;
  const width = 760;
  const height = 220;
  const padding = { top: 22, right: 18, bottom: 32, left: 34 };
  const max = Math.max(...items.map(item => item.count), 1);
  const x = (index: number) => padding.left + (index / Math.max(items.length - 1, 1)) * (width - padding.left - padding.right);
  const y = (count: number) => height - padding.bottom - (count / max) * (height - padding.top - padding.bottom);
  const points = items.map((item, index) => `${x(index)},${y(item.count)}`).join(" ");
  const labelStep = Math.max(1, Math.ceil(items.length / 7));
  return <div className="analytics-chart-wrap"><svg className="analytics-line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Video uploads over time"><line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} className="chart-axis" /><polyline points={`${padding.left},${height - padding.bottom} ${points} ${width - padding.right},${height - padding.bottom}`} className="chart-area" /><polyline points={points} className="chart-line" />{items.map((item, index) => <g key={item.date}><title>{`${formatDate(item.date)}: ${item.count} uploads`}</title><circle cx={x(index)} cy={y(item.count)} r="4" className="chart-point" />{(index % labelStep === 0 || index === items.length - 1) && <text x={x(index)} y={height - 9} textAnchor="middle" className="chart-label">{item.date.slice(5)}</text>}</g>)}</svg></div>;
}

function V2StatusDonut({ items }: { items: { label: string; count: number }[] }) {
  const groups = [
    { label: "Completed", color: "#34D399", count: items.filter(item => item.label === "COMPLETED").reduce((sum, item) => sum + item.count, 0) },
    { label: "Processing", color: "#22D3EE", count: items.filter(item => ["PROCESSING", "VALIDATING", "FFMPEG_PROCESSING", "READY_FOR_AI", "AI_PROCESSING"].includes(item.label)).reduce((sum, item) => sum + item.count, 0) },
    { label: "Uploaded / pending", color: "#FBBF24", count: items.filter(item => ["UPLOADING", "UPLOADED"].includes(item.label)).reduce((sum, item) => sum + item.count, 0) },
    { label: "Failed", color: "#F87171", count: items.filter(item => item.label === "FAILED").reduce((sum, item) => sum + item.count, 0) },
  ];
  const total = groups.reduce((sum, item) => sum + item.count, 0);
  let offset = 0;
  const gradient = groups.map(group => { const start = offset; offset += total ? group.count / total * 100 : 0; return `${group.color} ${start}% ${offset}%`; }).join(", ");
  return <div className="status-donut-layout"><div className="status-donut" style={{ background: total ? `conic-gradient(${gradient})` : "#273244" }} role="img" aria-label={`${total} videos by processing status`}><div><strong>{total}</strong><span>videos</span></div></div><div className="status-legend">{groups.map(group => <div key={group.label}><span className="legend-dot" style={{ background: group.color }} /><span>{group.label}</span><strong>{group.count}</strong></div>)}</div></div>;
}

function Pipeline({ analytics }: { analytics: AnalyticsDashboard }) {
  const stages = [
    { label: "Videos", icon: Clapperboard, data: analytics.processing_insights.videos, tone: "violet" },
    { label: "Transcripts", icon: FileText, data: analytics.processing_insights.transcripts, tone: "cyan" },
    { label: "AI summaries", icon: Sparkles, data: analytics.processing_insights.summaries, tone: "amber" },
    { label: "Key moments", icon: WandSparkles, data: analytics.processing_insights.key_moments, tone: "rose" },
  ];
  return <><div className="pipeline">{stages.map((stage, index) => <div className="pipeline-step" key={stage.label}><article className={`pipeline-card ${stage.tone}`}><span><stage.icon size={18} /></span><small>{stage.label}</small><strong>{stage.data.count}</strong>{index > 0 && <em>{stage.data.coverage_percentage}% coverage</em>}</article>{index < stages.length - 1 && <span className="pipeline-arrow" aria-hidden="true">↓</span>}</div>)}</div><Phase5Charts analytics={analytics} onVideoSelect={() => undefined} /></>;
}

function InsightBars({ items }: { items: { label: string; count: number }[] }) {
  const maximum = Math.max(...items.map(item => item.count), 1);
  if (!items.length) return <div className="analytics-empty-block">No content insights available yet.</div>;
  return <div className="insight-bars">{items.slice(0, 10).map(item => <div className="insight-bar" key={item.label}><div><span>{item.label}</span><strong>{item.count}</strong></div><span className="insight-track"><i style={{ width: `${Math.max(item.count / maximum * 100, 3)}%` }} /></span></div>)}</div>;
}

function Phase5HorizontalChart({ title, items, suffix = "", onSelect }: { title: string; items: { label: string; value: number; detail?: string }[]; suffix?: string; onSelect?: (label: string) => void }) {
  if (!items.length) return <div className="analytics-empty-block">No data available for this period.</div>;
  const sorted = [...items].sort((left, right) => right.value - left.value).slice(0, 10);
  const maximum = Math.max(...sorted.map(item => item.value), 1);
  return <div className="phase5-horizontal-chart" aria-label={title}>{sorted.map(item => <button type="button" className="phase5-chart-row" key={item.label} onClick={() => onSelect?.(item.label)} title={item.detail ?? `${item.label}: ${item.value}${suffix}`}><span className="phase5-chart-label">{item.label}</span><span className="phase5-chart-track"><i style={{ width: `${Math.max(item.value / maximum * 100, 3)}%` }} /></span><strong>{Number.isInteger(item.value) ? item.value : item.value.toFixed(2)}{suffix}</strong></button>)}</div>;
}

function Phase5ContentActivity({ items }: { items: { date: string; transcripts: number; summaries: number; key_moments: number }[] }) {
  if (!items.length) return <div className="analytics-empty-block">No AI activity available for this period.</div>;
  const width = 760;
  const height = 220;
  const padding = { top: 18, right: 18, bottom: 32, left: 30 };
  const maximum = Math.max(...items.flatMap(item => [item.transcripts, item.summaries, item.key_moments]), 1);
  const x = (index: number) => padding.left + index / Math.max(items.length - 1, 1) * (width - padding.left - padding.right);
  const y = (value: number) => height - padding.bottom - value / maximum * (height - padding.top - padding.bottom);
  const series = [{ key: "transcripts", label: "Transcripts", color: "#22D3EE" }, { key: "summaries", label: "Summaries", color: "#FBBF24" }, { key: "key_moments", label: "Key moments", color: "#FB7185" }] as const;
  return <div><div className="phase5-chart-legend">{series.map(item => <span key={item.key}><i style={{ background: item.color }} />{item.label}</span>)}</div><svg className="analytics-line-chart phase5-multi-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="AI activity over time"><line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} className="chart-axis" />{series.map(item => { const points = items.map((entry, index) => `${x(index)},${y(entry[item.key])}`).join(" "); return <polyline key={item.key} points={points} className="phase5-series-line" style={{ stroke: item.color }} />; })}{items.map((item, index) => <g key={item.date}><title>{`${formatDate(item.date)}: ${item.transcripts} transcripts, ${item.summaries} summaries, ${item.key_moments} key moments`}</title>{series.map(seriesItem => <circle key={seriesItem.key} cx={x(index)} cy={y(item[seriesItem.key])} r="3" style={{ fill: seriesItem.color }} />)}{(index % Math.max(1, Math.ceil(items.length / 7)) === 0 || index === items.length - 1) && <text x={x(index)} y={height - 9} textAnchor="middle" className="chart-label">{item.date.slice(5)}</text>}</g>)}</svg></div>;
}

function Phase5CompressionChart({ data }: { data: { average_transcript_words: number; average_summary_words: number; compression_ratio: number } }) {
  return <div className="compression-chart"><div className="compression-bars"><div><span>Transcript words</span><i style={{ height: `${data.average_transcript_words ? 100 : 0}%` }} /><strong>{Math.round(data.average_transcript_words).toLocaleString()}</strong></div><div><span>Summary words</span><i style={{ height: `${data.average_transcript_words ? Math.max(data.average_summary_words / data.average_transcript_words * 100, 3) : 0}%` }} /><strong>{Math.round(data.average_summary_words).toLocaleString()}</strong></div></div><p>Average summary compression: <strong>{(data.compression_ratio * 100).toFixed(1)}%</strong> of transcript length</p></div>;
}

function Phase5Charts({ analytics, onVideoSelect }: { analytics: AnalyticsDashboard; onVideoSelect: (filename: string) => void }) {
  const keyMomentItems = analytics.key_moment_insights.by_video.map(item => ({ label: item.label, value: item.count }));
  const scoreItems = analytics.recent_videos.map(video => ({ label: video.filename, value: video.ai_score, detail: `${video.filename}: ${video.ai_score}/100` }));
  const keywordItems = analytics.keyword_intelligence.map(item => ({ label: item.keyword, value: item.frequency, detail: `${item.frequency} occurrences across ${item.video_count} videos` }));
  return <div className="analytics-chart-grid"><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Keyword frequency</span><h2>Most used terms</h2></div><span className="section-note">Top 10</span></div><Phase5HorizontalChart title="Keyword frequency" items={keywordItems} /></article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Key moments by video</span><h2>Where the signal is</h2></div><span className="section-note">Top 10</span></div><Phase5HorizontalChart title="Key moments by video" items={keyMomentItems} onSelect={onVideoSelect} /></article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Intelligence comparison</span><h2>AI score by video</h2></div><span className="section-note">0–100 scale</span></div><Phase5HorizontalChart title="AI content intelligence by video" items={scoreItems} suffix=" / 100" onSelect={onVideoSelect} /></article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Compression insight</span><h2>Transcript vs summary</h2></div></div><Phase5CompressionChart data={analytics.compression_insights} /></article><article className="analytics-panel analytics-chart-wide"><div className="section-heading"><div><span className="eyebrow">AI activity trend</span><h2>Content generated over time</h2></div></div><Phase5ContentActivity items={analytics.content_activity} /></article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Importance distribution</span><h2>Key moment quality</h2></div></div><Phase5HorizontalChart title="Key moment importance" items={analytics.importance_distribution.map(item => ({ label: item.label, value: item.count, detail: `${item.count} moments · ${item.average_importance} average importance` }))} /></article></div>;
}

function LoadingAnalytics() {
  return <section className="simple-page analytics-page"><div className="analytics-skeleton-head"><span /><span /><span /></div><div className="analytics-skeleton-grid">{Array.from({ length: 8 }, (_, index) => <div className="analytics-skeleton-card" key={index}><span /><strong /><small /></div>)}</div><div className="analytics-skeleton-panel" /></section>;
}

function Phase3AnalyticsPage() {
  const { token, user } = useAuth();
  const [analytics, setAnalytics] = useState<AnalyticsDashboard | null>(null);
  const [rangeKey, setRangeKey] = useState<AnalyticsRangeKey>("all");
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !user) return;
    let active = true;
    setLoading(true);
    setError(null);
    const loader = user.role === "Administrator" ? getAdminAnalytics : getCreatorAnalytics;
    loader(token, rangeFor(rangeKey)).then(result => { if (active) setAnalytics(result); }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "Unable to load analytics."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, user, rangeKey, refreshKey]);

  if (loading && !analytics) return <LoadingAnalytics />;
  if (error) return <section className="simple-page analytics-page"><div className="analytics-error"><span className="eyebrow">Analytics unavailable</span><h1>Unable to load analytics</h1><p>{error}</p><button className="primary-button" type="button" onClick={() => setRefreshKey(value => value + 1)}><RefreshCw size={16} /> Try again</button></div></section>;
  if (!analytics) return null;

  const { overview, video_analytics: video, transcript_insights: transcripts, keyword_insights: keywords, summary_insights: summaries, key_moment_insights: moments } = analytics;
  const noVideos = overview.total_videos === 0;
  const ranges: { key: AnalyticsRangeKey; label: string }[] = [{ key: "7d", label: "7 Days" }, { key: "30d", label: "30 Days" }, { key: "90d", label: "90 Days" }, { key: "all", label: "All Time" }];
  return <section className="simple-page analytics-page"><header className="analytics-header"><div><span className="eyebrow">ClipMind AI · Video intelligence</span><h1>Analytics</h1><p>Understand how your videos are processed, summarized, and transformed into useful insights.</p></div><div className="analytics-actions"><div className="range-control" aria-label="Analytics date range">{ranges.map(range => <button key={range.key} type="button" className={rangeKey === range.key ? "active" : ""} aria-pressed={rangeKey === range.key} onClick={() => setRangeKey(range.key)}>{range.label}</button>)}</div><button className="icon-button" type="button" aria-label="Refresh analytics" title="Refresh analytics" onClick={() => setRefreshKey(value => value + 1)} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""} /></button></div></header>{loading && <div className="analytics-refreshing" role="status"><RefreshCw size={14} className="spin" /> Refreshing live data</div>}{noVideos ? <div className="analytics-empty-state"><span className="analytics-empty-icon"><Video size={25} /></span><h2>No video analytics yet</h2><p>Upload your first video to start generating transcripts, summaries, key moments, and insights.</p><Link className="primary-button" to="/creator/upload"><Upload size={16} /> Upload Video</Link></div> : <><div className="analytics-section-heading"><span className="eyebrow">Overview</span><h2>Video intelligence at a glance</h2></div><div className="analytics-metric-grid"><V2Metric label="Videos analyzed" value={overview.total_videos} detail={`${overview.completed_videos} completed`} icon={Clapperboard} tone="violet" /><V2Metric label="Transcripts" value={overview.total_transcripts} detail={`${transcripts.total_words.toLocaleString()} words`} icon={FileText} tone="cyan" /><V2Metric label="AI summaries" value={overview.total_summaries} detail={`${summaries.generation_rate_percentage}% coverage`} icon={Sparkles} tone="amber" /><V2Metric label="Key moments" value={overview.total_key_moments} detail={`${moments.videos_with_key_moments} videos surfaced`} icon={WandSparkles} tone="rose" /></div><div className="analytics-v2-grid"><article className="analytics-panel analytics-v2-wide"><div className="section-heading"><div><span className="eyebrow">Video activity</span><h2>Uploads over time</h2></div><span className="section-note">{overview.total_duration_seconds ? formatDuration(overview.total_duration_seconds) : "No duration yet"} total runtime</span></div><V2ActivityChart items={video.upload_activity} /></article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Processing status</span><h2>Pipeline distribution</h2></div></div><V2StatusDonut items={video.status_distribution} /></article><article className="analytics-panel analytics-v2-wide"><div className="section-heading"><div><span className="eyebrow">AI processing insights</span><h2>From video to understanding</h2></div><span className="section-note">Live coverage from stored content</span></div><Pipeline analytics={analytics} /></article><article className="analytics-panel analytics-v2-wide"><div className="section-heading"><div><span className="eyebrow">Content intelligence</span><h2>What your videos are talking about</h2></div><span className="section-note">Top recurring terms</span></div><div className="analytics-content-grid"><div><h3>Keyword insights</h3><InsightBars items={keywords.map(item => ({ label: item.keyword, count: item.frequency }))} /></div><div className="transcript-stats"><h3>Transcript insights</h3><div className="stat-detail-grid"><span><strong>{transcripts.total_words.toLocaleString()}</strong>Total words</span><span><strong>{Math.round(transcripts.average_words_per_transcript).toLocaleString()}</strong>Avg / transcript</span><span><strong>{transcripts.longest_transcript_words.toLocaleString()}</strong>Longest</span><span><strong>{transcripts.shortest_transcript_words.toLocaleString()}</strong>Shortest</span><span><strong>{transcripts.total_characters.toLocaleString()}</strong>Total characters</span></div></div></div></article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Summary intelligence</span><h2>AI summary insights</h2></div></div><div className="insight-highlight"><strong>{summaries.generation_rate_percentage}%</strong><span>summary coverage</span></div><div className="stat-detail-grid compact"><span><strong>{summaries.total_summaries}</strong>Total summaries</span><span><strong>{summaries.completed_summaries}</strong>Completed</span><span><strong>{Math.round(summaries.average_summary_words).toLocaleString()}</strong>Avg words</span><span><strong>{summaries.total_summary_words.toLocaleString()}</strong>Total words</span></div><h3 className="subsection-title">Recent AI summaries</h3><div className="mini-list">{summaries.recent_activity.slice(0, 4).map(summary => <div key={summary.id}><span>{summary.filename}</span><small>{summary.status} · {formatDate(summary.created_at)}</small></div>)}</div></article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Key moment intelligence</span><h2>Highlights by video</h2></div></div><div className="stat-detail-grid compact"><span><strong>{moments.total_key_moments}</strong>Total moments</span><span><strong>{moments.average_per_video}</strong>Avg / video</span><span><strong>{moments.average_importance.toFixed(2)}</strong>Avg importance</span><span><strong>{formatDuration(moments.total_duration_seconds)}</strong>Highlight duration</span></div><div className="subsection-title">Moments by video</div><InsightBars items={moments.by_video} /></article><article className="analytics-panel analytics-v2-wide"><div className="section-heading"><div><span className="eyebrow">Recent AI activity</span><h2>What just happened</h2></div></div>{analytics.recent_activity.length ? <div className="activity-timeline">{analytics.recent_activity.map(event => <div key={`${event.type}-${event.timestamp}-${event.video_id}`}><span className="timeline-icon"><Activity size={14} /></span><div><strong>{event.description}</strong><small>{event.video_name} · {formatDate(event.timestamp)}</small></div><em>{event.type.replaceAll("_", " ")}</em></div>)}</div> : <div className="analytics-empty-block">No recent AI activity in this range.</div>}</article><article className="analytics-panel analytics-v2-wide"><div className="section-heading"><div><span className="eyebrow">Recent content</span><h2>Recent videos</h2></div><span className="section-note">{analytics.recent_videos.length} shown</span></div><div className="recent-videos-table-wrap"><table className="analytics-video-table"><thead><tr><th>Video</th><th>Duration</th><th>Processing</th><th>Transcript</th><th>Summary</th><th>Moments</th><th>Uploaded</th></tr></thead><tbody>{analytics.recent_videos.map(video => <tr key={video.id}><td><strong>{video.filename}</strong><small>{video.owner_name}</small></td><td>{formatDuration(video.duration_seconds)}</td><td><span className={`analytics-status ${video.status.toLowerCase()}`}>{video.status}</span></td><td>{video.transcript_status === "COMPLETED" ? "Ready" : video.transcript_status ?? "-"}</td><td>{video.summary_status === "COMPLETED" ? "Ready" : video.summary_status ?? "-"}</td><td>{video.key_moment_count}</td><td>{formatDate(video.uploaded_at)}</td></tr>)}</tbody></table></div></article></div></>}</section>;
}

function Phase4VideoDetail({ video, onClose }: { video: AnalyticsRecentVideo; onClose: () => void }) {
  return <div className="analytics-detail-backdrop" role="presentation" onClick={onClose}><aside className="analytics-detail-panel" role="dialog" aria-modal="true" aria-label={`${video.filename} intelligence details`} onClick={event => event.stopPropagation()}><button className="analytics-detail-close" type="button" aria-label="Close video details" onClick={onClose}>×</button><span className="eyebrow">Video overview</span><h2>{video.filename}</h2><p>{video.status} · Uploaded {formatDate(video.uploaded_at)}</p><div className="detail-score"><strong>{video.ai_score}</strong><span>/ 100<br />AI content intelligence</span></div><div className="detail-breakdown">{Object.entries(video.ai_score_components).map(([label, score]) => <div key={label}><span>{label}</span><strong>{Math.round(score)}%</strong><i><em style={{ width: `${score}%` }} /></i></div>)}</div><div className="detail-columns"><section><span>Transcript</span><strong>{video.transcript_status ?? "No transcript"}</strong><small>{video.transcript_word_count.toLocaleString()} words · {video.transcript_character_count.toLocaleString()} chars</small></section><section><span>Summary</span><strong>{video.summary_status === "COMPLETED" ? "Generated" : video.summary_status ?? "Not generated"}</strong><small>{video.summary_word_count.toLocaleString()} words · {video.main_points_count} main points</small></section><section><span>Key moments</span><strong>{video.key_moment_count}</strong><small>{video.average_importance.toFixed(2)} average importance · {video.highest_importance.toFixed(2)} highest</small></section><section><span>Content</span><strong>{video.topic_count} topics</strong><small>{video.top_keywords.join(", ") || "No keywords yet"}</small></section></div></aside></div>;
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
    loader(token, rangeFor(rangeKey)).then(result => { if (active) setAnalytics(result); }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "Unable to load analytics."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token, user, rangeKey, refreshKey]);

  if (loading && !analytics) return <LoadingAnalytics />;
  if (error) return <section className="simple-page analytics-page"><div className="analytics-error"><span className="eyebrow">Analytics unavailable</span><h1>Unable to load analytics</h1><p>{error}</p><button className="primary-button" type="button" onClick={() => setRefreshKey(value => value + 1)}><RefreshCw size={16} /> Try again</button></div></section>;
  if (!analytics) return null;

  const ranges: { key: AnalyticsRangeKey; label: string }[] = [{ key: "7d", label: "7 Days" }, { key: "30d", label: "30 Days" }, { key: "90d", label: "90 Days" }, { key: "all", label: "All Time" }];
  const noVideos = analytics.overview.total_videos === 0;
  return <section className="simple-page analytics-page"><header className="analytics-header"><div><span className="eyebrow">ClipMind AI · AI video intelligence center</span><h1>Analytics</h1><p>See what your videos contain, what the AI discovered, and what deserves attention next.</p></div><div className="analytics-actions"><div className="range-control" aria-label="Analytics date range">{ranges.map(range => <button key={range.key} type="button" className={rangeKey === range.key ? "active" : ""} aria-pressed={rangeKey === range.key} onClick={() => setRangeKey(range.key)}>{range.label}</button>)}</div><button className="icon-button" type="button" aria-label="Refresh analytics" title="Refresh analytics" onClick={() => setRefreshKey(value => value + 1)} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""} /></button></div></header>{loading && <div className="analytics-refreshing" role="status"><RefreshCw size={14} className="spin" /> Refreshing live data</div>}{noVideos ? <div className="analytics-empty-state"><span className="analytics-empty-icon"><Video size={25} /></span><h2>No video analytics yet</h2><p>Upload your first video to start generating transcripts, summaries, key moments, and insights.</p><Link className="primary-button" to="/creator/upload"><Upload size={16} /> Upload Video</Link></div> : <><div className="analytics-section-heading"><span className="eyebrow">Executive overview</span><h2>AI content intelligence at a glance</h2></div><div className="analytics-metric-grid"><V2Metric label="Videos analyzed" value={analytics.overview.total_videos} detail={`${analytics.overview.completed_videos} completed`} icon={Clapperboard} tone="violet" /><V2Metric label="Transcripts" value={analytics.overview.total_transcripts} detail={`${analytics.transcript_insights.total_words.toLocaleString()} words`} icon={FileText} tone="cyan" /><V2Metric label="AI summaries" value={analytics.overview.total_summaries} detail={`${analytics.summary_insights.generation_rate_percentage}% coverage`} icon={Sparkles} tone="amber" /><V2Metric label="Key moments" value={analytics.overview.total_key_moments} detail={`${analytics.key_moment_insights.videos_with_key_moments} videos surfaced`} icon={WandSparkles} tone="rose" /><article className="intelligence-score-card"><span className="eyebrow">AI content intelligence</span><strong>{analytics.intelligence_score.score}</strong><span>/ 100</span><p>{analytics.intelligence_score.explanation}</p></article></div><div className="analytics-phase4-grid"><article className="analytics-panel analytics-phase4-wide"><div className="section-heading"><div><span className="eyebrow">AI insights</span><h2>What deserves attention</h2></div></div><div className="ai-insights-grid">{analytics.ai_insights.length ? analytics.ai_insights.map(insight => <div className={`ai-insight ${insight.category.toLowerCase().replace(" ", "-")}`} key={`${insight.category}-${insight.title}`}><span>{insight.category}</span><strong>{insight.title}</strong><p>{insight.message}</p>{insight.metric && <em>{insight.metric}</em>}</div>) : <div className="analytics-empty-block">More content is needed to generate data-driven insights.</div>}</div></article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Topic intelligence</span><h2>Top content topics</h2></div></div><div className="topic-list">{analytics.top_topics.map(topic => <button type="button" key={topic.topic} onClick={() => setSelectedVideo(null)}><span><strong>{topic.topic}</strong><small>{topic.video_count} videos · {topic.frequency} occurrences</small></span><b>{topic.percentage}%</b></button>)}</div></article><article className="analytics-panel"><div className="section-heading"><div><span className="eyebrow">Advanced keywords</span><h2>Keyword intelligence</h2></div></div><div className="keyword-list">{analytics.keyword_intelligence.slice(0, 8).map(keyword => <div key={keyword.keyword}><span><strong>{keyword.keyword}</strong><small>{keyword.frequency} occurrences · {keyword.video_count} videos</small></span><b>{keyword.share_percentage}%</b></div>)}</div></article><article className="analytics-panel analytics-phase4-wide"><div className="section-heading"><div><span className="eyebrow">Video intelligence</span><h2>Compare your content</h2></div><span className="section-note">Select a row for details</span></div><div className="video-intelligence-table-wrap"><table className="video-intelligence-table"><thead><tr><th>Video</th><th>Duration</th><th>Words</th><th>Topics</th><th>Summary</th><th>Moments</th><th>AI score</th></tr></thead><tbody>{analytics.recent_videos.map(video => <tr key={video.id} onClick={() => setSelectedVideo(video)} tabIndex={0} onKeyDown={event => { if (event.key === "Enter") setSelectedVideo(video); }}><td><strong>{video.filename}</strong><small>{video.status} · {formatDate(video.uploaded_at)}</small></td><td>{formatDuration(video.duration_seconds)}</td><td>{video.transcript_status ? video.transcript_word_count.toLocaleString() : "No transcript"}</td><td>{video.topic_count}</td><td>{video.summary_status === "COMPLETED" ? "Ready" : "Not generated"}</td><td>{video.key_moment_count}</td><td><b className="score-pill">{video.ai_score}</b></td></tr>)}</tbody></table></div></article></div><article className="analytics-panel analytics-phase4-wide"><div className="section-heading"><div><span className="eyebrow">Pipeline detail</span><h2>From video to understanding</h2></div></div><Pipeline analytics={analytics} /></article></>}{selectedVideo && <Phase4VideoDetail video={selectedVideo} onClose={() => setSelectedVideo(null)} />}</section>;
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
  const [isDragging, setIsDragging] = useState(false);

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
      } catch { if (requestId === historyRequestRef.current) setVideos([]); }
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
      await deleteVideo(token, selectedEvent.video_id);
      setEvents(current => current.filter(event => event.video_id !== selectedEvent.video_id));
      setVideos(current => current.filter(video => video.id !== selectedEvent.video_id));
      setSelectedEvent(null);
      setNotice("Video and associated data deleted successfully.");
      window.setTimeout(() => setNotice(null), 3000);
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason.message : "Video could not be deleted.");
    } finally { setDeletingVideoId(null); }
  }

  const latestEvents = Array.from(events.reduce((latest, event) => {
    const previous = latest.get(event.video_id);
    if (!previous || new Date(event.timestamp).getTime() > new Date(previous.timestamp).getTime()) latest.set(event.video_id, event);
    return latest;
  }, new Map<string, UploadHistoryEvent>()).values());

  const filteredEvents = latestEvents
    .filter(event => {
      if (statusFilter === "ALL") return true;
      const status = event.status.toUpperCase();
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
    const status = event.status.toUpperCase();
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
      {loading && <div className="history-skeleton-list" role="status" aria-label="Loading upload history">{[1, 2, 3].map(item => <div className="history-skeleton-row" key={item}><span /><span /><span /><span /></div>)}</div>}
        {!loading && latestEvents.length === 0 && <div className="feature-placeholder history-empty"><span className="eyebrow">No uploads yet</span><h2>Start your video workspace</h2><p>Upload your first video to start generating transcripts, summaries, and key moments.</p><Link className="primary-button" to="/creator/upload">Upload Video</Link></div>}
      {!loading && latestEvents.length > 0 && filteredEvents.length === 0 && <div className="history-empty-filter">No uploads match the current search and filters.</div>}
      {!loading && filteredEvents.length > 0 && <div className="history-table-wrap"><table className="history-table"><thead><tr><th>Video</th>{administrator && <th>Owner</th>}<th>Uploaded</th><th>Size</th><th>Duration</th><th>Status</th><th>Actions</th></tr></thead><tbody>{filteredEvents.map(event => { const video = videos.find(item => item.id === event.video_id); return <tr key={event.id}><td><div className="history-video-cell"><span className="history-file-icon"><FileText size={17} /></span><span><strong>{event.filename}</strong><small>{event.filename.split(".").pop()?.toUpperCase() || "FILE"}</small></span></div></td>{administrator && <td>{event.owner_name}</td>}<td><strong>{new Date(event.timestamp).toLocaleDateString()}</strong><small>{new Date(event.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</small></td><td>{video ? formatFileSize(video.file_size_bytes) : "Not available"}</td><td>{video ? formatDuration(video.duration_seconds) : "Not available"}</td><td><span className={`event-status ${event.status.toLowerCase()}`}>{event.status}</span><small className="history-note">{event.notes ?? "No event notes"}</small></td><td><div className="history-actions">{video && <button className="mini-button" type="button" onClick={() => setSelectedVideo(video)} aria-label={`Play ${event.filename}`}>Play</button>}<Link className="mini-button neutral" to={administrator ? `/admin/activity` : `/creator/transcripts/${event.video_id}`}>View</Link><button className="mini-button danger-text" type="button" onClick={() => setSelectedEvent(event)} disabled={deletingVideoId === event.video_id}>Delete</button></div></td></tr>; })}</tbody></table></div>}
    </>}
    {selectedEvent && <DeleteConfirmationModal video={videos.find(video => video.id === selectedEvent.video_id) ?? { id: selectedEvent.video_id, filename: selectedEvent.filename, mime_type: "", file_size_bytes: 0, duration_seconds: null, processing_status: selectedEvent.status, uploaded_at: selectedEvent.timestamp, owner_id: selectedEvent.owner_id, owner_name: selectedEvent.owner_name }} isDeleting={deletingVideoId === selectedEvent.video_id} onConfirm={() => void confirmDelete()} onCancel={() => setSelectedEvent(null)} />}
    {selectedVideo && <VideoPlayerModal video={selectedVideo} onClose={() => setSelectedVideo(null)} />}
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

  return <section className="simple-page status-page"><span className="eyebrow">Creator studio</span><h1>Processing status</h1><p className="feature-description">Track the current lifecycle state of your uploaded videos. AI processing is not started by this view.</p>{loading && <div className="feature-status" role="status"><span className="status-dot" />Loading current statuses...</div>}{error && <div className="notice" role="alert">{error}</div>}{!loading && !error && videos.length === 0 && <div className="feature-placeholder"><span className="eyebrow">Nothing processing</span><h2>No uploaded videos yet</h2><p>Upload a video to begin tracking its lifecycle.</p></div>}{!loading && !error && videos.length > 0 && <div className="status-list">{videos.map(video => <article className="status-card" key={video.id}><div><strong>{video.filename}</strong><small>Updated {new Date(video.updated_at).toLocaleString()}</small></div><span className={`event-status ${video.processing_status.toLowerCase()}`}>{video.processing_status}</span><p>{video.latest_note ?? "No status notes yet."}</p></article>)}</div>}</section>;
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

function VideoPlayerModal({ video, onClose, initialTime }: { video: VideoListItem; onClose: () => void; initialTime?: number }) {
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const videoRef = useRef<HTMLVideoElement>(null);
  const mediaUrl = getVideoMediaUrl(video.id, video.owner_id, video.filename, video.storage_key);
  const formatSupportsHtmlPlayback = /\.(mp4|webm|ogg|mov)$/i.test(video.filename) || /video\/(mp4|webm|ogg|quicktime)/i.test(video.mime_type);

  useEffect(() => {
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onClose]);

  useEffect(() => {
    if (!videoRef.current) return;
    const player = videoRef.current;
    const handleLoadedData = () => {
      setIsLoading(false);
      setError(null);
    };
    const handleError = () => {
      setIsLoading(false);
      setError(formatSupportsHtmlPlayback
        ? "This video could not be loaded. Please verify the uploaded file is still available."
        : "This file format is not browser-playable in HTML5. Please convert it to MP4 or WebM and upload again.");
    };
    player.addEventListener("loadeddata", handleLoadedData);
    player.addEventListener("error", handleError);
    return () => {
      player.removeEventListener("loadeddata", handleLoadedData);
      player.removeEventListener("error", handleError);
    };
  }, [formatSupportsHtmlPlayback]);

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
        {!formatSupportsHtmlPlayback && !error && (
          <div className="notice" role="alert">
            This file format is not browser-playable in HTML5. Please convert it to MP4 or WebM for playback.
          </div>
        )}
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
            setError(formatSupportsHtmlPlayback
              ? "This video could not be loaded. Please verify the uploaded file is still available."
              : "This file format is not browser-playable in HTML5. Please convert it to MP4 or WebM for playback.");
          }}
          src={mediaUrl}
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

function TranscriptModalContent({ data, onRetry, onSeek, onClose }: { data: AnalysisCache; onRetry: () => void; onSeek: (time: number) => void; onClose: () => void }) {
  const [search, setSearch] = useState("");
  const transcript = data.transcript;
  const query = search.trim().toLowerCase();
  const segments = transcript?.segments.filter(segment => !query || segment.text.toLowerCase().includes(query)) ?? [];

  return (
    <>
      {data.loading && <div className="analysis-state" role="status"><span className="status-loader" />Loading transcript...</div>}
      {!data.loading && data.error && <div className="analysis-state analysis-error" role="alert"><strong>Unable to load transcript</strong><p>{data.error}</p><button className="secondary-button" type="button" onClick={onRetry}>Retry</button></div>}
      {!data.loading && !data.error && !transcript && <div className="analysis-state"><FileText size={22} /><strong>No transcript available yet.</strong><p>Generate the transcript to view it here.</p></div>}
      {!data.loading && !data.error && transcript && (
        <>
          <div className="analysis-toolbar">
            <span className={`analysis-status ${transcript.status.toLowerCase()}`}>{analysisStatus(transcript.status)}</span>
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
        <div className="analysis-toolbar"><span className={`analysis-status ${summary.status.toLowerCase()}`}>{analysisStatus(summary.status)}</span></div>
        {summary.status === "FAILED" ? <div className="analysis-state analysis-error" role="alert"><strong>Summary generation failed</strong><p>{summary.error_message || "The summary could not be generated."}</p><button className="secondary-button" type="button" onClick={onRetry}>Retry</button></div> : <div className="summary-modal-content"><section><span className="analysis-kicker">Overview</span><p>{summary.overview || summary.content}</p></section><section><span className="analysis-kicker">Key Takeaways</span><ul>{summary.key_takeaways.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></section><section><span className="analysis-kicker">Important Points</span><ol>{summary.main_points.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ol></section></div>}
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
        <div className="analysis-moment-list key-moments-list">{data.keyMoments.map((moment, index) => { const score = Math.max(0, Math.min(1, moment.importance_score)); return <article className="analysis-moment" key={moment.id}><div className="analysis-moment-index"><span className="moment-index">{String(index + 1).padStart(2, "0")}</span></div><div className="analysis-moment-main"><div className="analysis-moment-heading"><h3>{moment.title}</h3>{moment.topic && <span className="topic-chip">{moment.topic}</span>}</div><p>{moment.description || moment.transcript_text}</p><div className="analysis-moment-meta"><span><Clock3 size={13} /> {formatAnalysisTime(moment.start_time)} <span aria-hidden="true">→</span> {formatAnalysisTime(moment.end_time)}</span><span>Importance</span></div><div className="importance-track" aria-label={`Importance ${Math.round(score * 100)} percent`}><span style={{ width: `${Math.round(score * 100)}%` }} /></div></div><div className="analysis-moment-action"><span className="analysis-score">{Math.round(score * 100)}%</span><button className="primary-button compact-button" type="button" onClick={() => onWatch(moment)}><CirclePlay size={14} />Watch Moment</button></div></article>; })}</div>
      </>}
    </>
  );
}

export function VideoLibraryPage({ heading, description }: { heading: string; description: string }) {
  const { token } = useAuth();
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
  const startedTranscriptIdsRef = useRef(new Set<string>());
  const transcriptGenerationRunningRef = useRef(false);
  const loadingAnalysisRef = useRef(new Set<string>());

  function analysisKey(videoId: string, kind: AnalysisKind) {
    return `${videoId}:${kind}`;
  }

  function openAnalysis(kind: AnalysisKind, video: VideoListItem) {
    setActiveAnalysis({ kind, video });
    const key = analysisKey(video.id, kind);
    if (analysisCache[key] || loadingAnalysisRef.current.has(key)) return;
    loadingAnalysisRef.current.add(key);
    setAnalysisCache(current => ({ ...current, [key]: { transcript: null, summary: null, keyMoments: [], loading: true, error: null } }));
    void loadAnalysis(kind, video);
  }

  async function loadAnalysis(kind: AnalysisKind, video: VideoListItem) {
    if (!token) return;
    const key = analysisKey(video.id, kind);
    try {
      if (kind === "transcript") {
        const transcript = await getTranscript(token, video.id);
        setAnalysisCache(current => ({ ...current, [key]: { ...(current[key] ?? { transcript: null, summary: null, keyMoments: [], loading: false, error: null }), transcript, loading: false, error: null } }));
      } else if (kind === "summary") {
        const summary = await getSummary(token, video.id);
        setAnalysisCache(current => ({ ...current, [key]: { ...(current[key] ?? { transcript: null, summary: null, keyMoments: [], loading: false, error: null }), summary, loading: false, error: null } }));
      } else {
        const keyMoments = await getKeyMoments(token, video.id);
        setAnalysisCache(current => ({ ...current, [key]: { ...(current[key] ?? { transcript: null, summary: null, keyMoments: [], loading: false, error: null }), keyMoments, loading: false, error: null } }));
      }
      loadingAnalysisRef.current.delete(key);
    } catch (reason) {
      const apiError = reason instanceof ApiError && reason.status === 404 ? null : reason instanceof Error ? reason.message : "The analysis could not be loaded.";
      setAnalysisCache(current => ({ ...current, [key]: { ...(current[key] ?? { transcript: null, summary: null, keyMoments: [], loading: false, error: null }), loading: false, error: apiError } }));
      loadingAnalysisRef.current.delete(key);
    }
  }

  function retryAnalysis() {
    if (!activeAnalysis) return;
    const { kind, video } = activeAnalysis;
    const key = analysisKey(video.id, kind);
    loadingAnalysisRef.current.add(key);
    setAnalysisCache(current => ({ ...current, [key]: { transcript: null, summary: null, keyMoments: [], loading: true, error: null } }));
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
        return /processing|pending|in_progress|uploaded/i.test(video.processing_status) ? "processing" : "not_generated";
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
      const pendingVideo = nextStates
        .map(([videoId, state]) => ({ videoId, state, video: nextVideos.find(item => item.id === videoId) }))
        .find(({ state, videoId, video }) => state === "processing" && video?.processing_status === "UPLOADED" && !startedTranscriptIdsRef.current.has(videoId));
      if (pendingVideo && !transcriptGenerationRunningRef.current) {
        const { videoId } = pendingVideo;
        startedTranscriptIdsRef.current.add(videoId);
        transcriptGenerationRunningRef.current = true;
        void generateTranscript(token, videoId)
          .catch(() => undefined)
          .finally(() => {
            transcriptGenerationRunningRef.current = false;
            void loadVideos(false);
          });
      }
      if (nextStates.some(([, state]) => state === "processing")) {
        if (pollingRef.current) clearTimeout(pollingRef.current);
        pollingRef.current = window.setTimeout(() => {
          pollingRef.current = null;
          void loadVideos(false);
        }, 3000);
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
    const transcriptState = transcriptStates[video.id] ?? (getTranscriptState(video.processing_status) === "transcript_ready" ? "ready" : "not_generated");

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
      await deleteVideo(token, selectedVideoForDelete.id);
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
  }, [token]);

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
            const state = transcriptStates[video.id] ?? (getTranscriptState(video.processing_status) === "transcript_ready" ? "ready" : /processing|pending|in_progress|uploaded/i.test(video.processing_status) ? "processing" : "not_generated");
            const ready = state === "ready";
            const processing = state === "processing";
            const failed = state === "failed";
            const transcriptStatusLabel = ready ? "Ready" : processing ? "Processing" : failed ? "Failed" : "Waiting";
            const transcriptStatusTone = ready ? "success" : processing ? "warning" : failed ? "danger" : "neutral";
            const summaryStatusLabel = ready ? "Ready" : "Waiting";
            const summaryStatusTone = ready ? "success" : "neutral";
            const momentsStatusLabel = ready ? "Ready" : "Waiting";
            const momentsStatusTone = ready ? "success" : "neutral";
            const mediaUrl = getVideoMediaUrl(video.id, video.owner_id, video.filename, video.storage_key);

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
          {activeAnalysis.kind === "transcript" && <TranscriptModalContent data={analysisCache[analysisKey(activeAnalysis.video.id, activeAnalysis.kind)] ?? { transcript: null, summary: null, keyMoments: [], loading: true, error: null }} onRetry={retryAnalysis} onSeek={time => { setActiveAnalysis(null); setPlaybackStartTime(time); setSelectedVideoToPlay(activeAnalysis.video); }} onClose={() => setActiveAnalysis(null)} />}
          {activeAnalysis.kind === "summary" && <SummaryModalContent data={analysisCache[analysisKey(activeAnalysis.video.id, activeAnalysis.kind)] ?? { transcript: null, summary: null, keyMoments: [], loading: true, error: null }} onRetry={retryAnalysis} onGenerate={() => void handleGenerateSummaryForLibrary(activeAnalysis.video)} />}
          {activeAnalysis.kind === "keyMoments" && <KeyMomentsModalContent data={analysisCache[analysisKey(activeAnalysis.video.id, activeAnalysis.kind)] ?? { transcript: null, summary: null, keyMoments: [], loading: true, error: null }} durationSeconds={activeAnalysis.video.duration_seconds} onRetry={retryAnalysis} onGenerate={() => void handleGenerateMomentsForLibrary(activeAnalysis.video)} onWatch={watchMoment} />}
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
    if (video && /processing|pending|in_progress/i.test(video.processing_status)) return "PROCESSING";
    if (video && /failed|error/i.test(video.processing_status)) return "FAILED";
    return "NOT_STARTED";
  }, [transcript, video]);

  const summaryState = useMemo(() => {
    if (summary?.status === "FAILED") return "FAILED";
    if (summary) return "READY";
    if (transcriptState === "READY") return "WAITING";
    if (transcriptState === "PROCESSING" || (video && /processing|pending|in_progress/i.test(video.processing_status))) return "PROCESSING";
    return "WAITING";
  }, [summary, transcriptState, video]);

  const keyMomentsState = useMemo(() => {
    if (moments.length > 0) return "READY";
    if (transcriptState === "READY") return "WAITING";
    if (transcriptState === "PROCESSING" || (video && /processing|pending|in_progress/i.test(video.processing_status))) return "PROCESSING";
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
        if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
          setError("Your session has expired. Please log in again.");
          return;
        }
        if (!(reason instanceof ApiError && /not found|does not exist/i.test(reason.message))) {
          setTranscript(null);
        }
      }

      try {
        const summaryResult = await getSummary(token, videoId);
        setSummary(summaryResult);
      } catch (reason) {
        if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
          setError("Your session has expired. Please log in again.");
          return;
        }
        setSummary(null);
      }

      try {
        const momentsResult = await getKeyMoments(token, videoId);
        setMoments(momentsResult.sort((a, b) => a.start_time - b.start_time));
      } catch (reason) {
        if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
          setError("Your session has expired. Please log in again.");
          return;
        }
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
    const shouldPoll = /processing|pending|in_progress/i.test(video.processing_status)
      || transcriptState === "PROCESSING"
      || summaryState === "PROCESSING"
      || keyMomentsState === "PROCESSING";

    if (!shouldPoll) return;
    if (pollingRef.current) window.clearTimeout(pollingRef.current);
    pollingRef.current = window.setTimeout(() => {
      void refreshData(true);
    }, 4000);

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

  function highlightText(text: string, query: string) {
    const trimmed = query.trim();
    if (!trimmed) return text;
    const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const pattern = new RegExp(`(${escaped})`, "ig");
    return text.split(pattern).map((part, index) =>
      part.toLowerCase() === trimmed.toLowerCase() ? <mark key={`${part}-${index}`}>{part}</mark> : <span key={`${part}-${index}`}>{part}</span>
    );
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
            <article>
              <h3>Overview</h3>
              <p>{summary.overview || summary.content}</p>
            </article>
            <article>
              <h3>Main points</h3>
              <ul>
                {summary.main_points.map((point, index) => <li key={`${point}-${index}`}>{point}</li>)}
              </ul>
            </article>
            <article>
              <h3>Key takeaways</h3>
              <ul>
                {summary.key_takeaways.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
              </ul>
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
                  <p>{moment.description}</p>
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
            <h3>Overview</h3>
            <p>{summary.overview || summary.content}</p>
          </article>
          <article className="result-card">
            <h3>📌 Main Points</h3>
            <ul className="result-list">
              {summary.main_points.map((point, index) => <li key={`${point}-${index}`}>{point}</li>)}
            </ul>
          </article>
          <article className="result-card">
            <h3>💡 Key Takeaways</h3>
            <ul className="result-list">
              {summary.key_takeaways.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
            </ul>
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
        setMoments(result.sort((a, b) => a.start_time - b.start_time));
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
                <p>{moment.description}</p>
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
  return <main className="login-page"><div className="login-art"><div className="brand"><span className="brand-mark"><Clapperboard size={18} /></span><span>ClipMind <em>AI</em></span></div><div className="art-copy"><span className="eyebrow">Start your workspace</span><h1>Give every frame somewhere useful to go.</h1><p>Create a role-aware ClipMind account for making, learning, teaching, or operating.</p></div></div><div className="login-panel"><div className="form-wrap"><span className="eyebrow">New account</span><h2>Join ClipMind</h2><p className="form-intro">Your role determines the workspace and permissions you receive.</p><form onSubmit={submit}><label>👤 Full name<input value={form.full_name} onChange={event => update("full_name", event.target.value)} required /></label><label>📧 Email<input type="email" value={form.email} onChange={event => update("email", event.target.value)} required /></label><label>🎭 Role<select value={form.role} onChange={event => update("role", event.target.value)}><option>Content Creator</option><option>Learner</option><option>Educator</option><option>Administrator</option></select></label><label>🔐 Password<input type="password" value={form.password} onChange={event => update("password", event.target.value)} minLength={8} required /></label><label>🔐 Confirm password<input type="password" value={form.confirm_password} onChange={event => update("confirm_password", event.target.value)} minLength={8} required /></label>{error && <p className="form-error" role="alert">{error}</p>}{success && <p className="upload-success" role="status">{success}</p>}<button className="primary-button" disabled={busy}>{busy ? "Creating account..." : "Create account"}</button></form><Link className="auth-link" to="/login">Back to sign in</Link></div></div></main>;
}

export function Profile() { const { user } = useAuth(); if (!user) return <Navigate to="/login" replace />; return <section className="simple-page"><span className="eyebrow">Account</span><h1>Your profile</h1><div className="profile-card"><div className="avatar">{user.full_name.slice(0, 1)}</div><div><h2>{user.full_name}</h2><p>{user.email}</p><span className="role-badge">{user.role}</span></div></div></section>; }

export { Dashboard };
