import { useEffect, useRef, useState } from "react";
import { CalendarDays, CirclePlay, Clock3, Download, FileText, HardDrive, Pencil, Search, Sparkles, User, Video } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import {
  downloadTranscript,
  generateKeyMoments,
  generateTranscript,
  getKeyMoments,
  getTranscript,
  getVideoMediaUrl,
  type KeyMoment,
  updateTranscript,
  type Transcript,
} from "../../services/api";
import { SummaryPanel } from "../summaries/SummaryPanel";

interface TranscriptPanelProps {
  videoId: string;
  ownerId: string;
  filename: string;
}

function formatTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes.toString().padStart(2, "0")}:${remainder}`;
}

function formatDuration(seconds: number | null) {
  if (!seconds || seconds <= 0) return "Duration pending";
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

function highlightText(text: string, query: string) {
  if (!query) return text;

  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`(${escaped})`, "ig");
  return text.split(pattern).map((part, index) =>
    part.toLowerCase() === query.toLowerCase() ? <mark key={`${part}-${index}`}>{part}</mark> : <span key={`${part}-${index}`}>{part}</span>
  );
}

export function TranscriptPanel({ videoId, ownerId, filename }: TranscriptPanelProps) {
  const { token, user } = useAuth();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [keyMoments, setKeyMoments] = useState<KeyMoment[]>([]);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const canEdit = user?.role === "Content Creator" || user?.role === "Educator" || user?.role === "Administrator";
  const canGenerate = canEdit;
  const transcriptReady = transcript?.status === "COMPLETED" && Array.isArray(transcript.segments) && transcript.segments.length > 0;
  const transcriptState = transcript?.status ? (transcript.status === "COMPLETED" ? "transcript_ready" : transcript.status === "FAILED" ? "transcript_failed" : "processing") : "transcript_missing";
  const videoUrl = getVideoMediaUrl(videoId, ownerId, filename, undefined);
  const uploadedByLabel = user?.full_name ?? ownerId;

  useEffect(() => {
    if (!token) return;
    getTranscript(token, videoId)
      .then(result => { setTranscript(result); setDraft(result.text); })
      .catch(reason => {
        if (!(reason instanceof Error) || !reason.message.toLowerCase().includes("does not exist")) {
          setError(reason instanceof Error ? reason.message : "Transcript could not be loaded.");
        }
      });

    getKeyMoments(token, videoId)
      .then(setKeyMoments)
      .catch(reason => {
        if (!(reason instanceof Error) || !reason.message.toLowerCase().includes("does not exist")) {
          setError(reason instanceof Error ? reason.message : "Key moments could not be loaded.");
        }
      });
  }, [token, videoId]);

  async function create() {
    if (!token) return;
    setBusy(true); setError(null); setMessage("Processing transcript...");
    try {
      const result = await generateTranscript(token, videoId);
      setTranscript(result); setDraft(result.text); setMessage("Transcript generated.");
    } catch (reason) {
      setMessage(null); setError(reason instanceof Error ? reason.message : "Transcript generation failed.");
    } finally { setBusy(false); }
  }

  async function save() {
    if (!token) return;
    setBusy(true); setError(null);
    try {
      const result = await updateTranscript(token, videoId, draft);
      setTranscript(result); setDraft(result.text); setEditing(false); setMessage("Transcript saved successfully.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Transcript could not be saved."); }
    finally { setBusy(false); }
  }

  async function download() {
    if (!token || !transcriptReady) {
      setError(transcriptState === "transcript_failed" ? "⚠️ Transcript generation failed." : transcriptState === "processing" ? "🎙️ Transcript is still being generated." : "📝 Transcript isn't available yet.");
      return;
    }
    try {
      const blob = await downloadTranscript(token, videoId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = "transcript.txt"; link.click(); URL.revokeObjectURL(url);
      setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Transcript download failed."); }
  }

  async function detectKeyMoments() {
    if (!token) return;
    setBusy(true); setError(null); setMessage("Detecting key moments...");
    try {
      const result = await generateKeyMoments(token, videoId);
      setKeyMoments(result); setMessage("Key moments detected.");
    } catch (reason) {
      setMessage(null); setError(reason instanceof Error ? reason.message : "Key moments could not be detected.");
    } finally { setBusy(false); }
  }

  async function playVideo() {
    const player = videoRef.current;
    if (!player) {
      setError("The video player is not available for this video.");
      return;
    }
    try {
      await player.play();
    } catch (reason) {
      console.error("[Play Video] Playback failed:", reason);
      setError("This video could not start playback. Check that the uploaded video is available.");
    }
  }

  async function playMoment(moment: KeyMoment) {
    const player = videoRef.current;
    if (!player) {
      setError("The video player is not available for this video.");
      return;
    }
    try {
      player.currentTime = moment.start_time;
      setCurrentTime(moment.start_time);
      await player.play();
    } catch (reason) {
      console.error("[Play Moment] Playback failed:", reason);
      setError("This key moment could not start playback. Check that the uploaded video is available.");
    }
  }

  function updatePlaybackTime(player: HTMLVideoElement) {
    setCurrentTime(player.currentTime);
  }

  const normalizedSearch = search.trim().toLowerCase();
  const segments = transcript?.segments.filter(segment => !normalizedSearch || segment.text.toLowerCase().includes(normalizedSearch)) ?? [];

  return <div className="transcript-workspace">
    <header className="transcript-header">
      <div className="workspace-title-wrap">
        <span className="eyebrow">Video workspace</span>
        <h2>🎬 {filename}</h2>
        <div className="workspace-meta">
          <span className="meta-chip"><User size={13} /> Uploaded by {uploadedByLabel}</span>
          <span className="meta-chip"><CalendarDays size={13} /> {transcript ? new Date(transcript.updated_at).toLocaleDateString() : "Processing"}</span>
          <span className="meta-chip"><Clock3 size={13} /> {formatDuration(transcript && transcript.segments.length > 0 ? transcript.segments[transcript.segments.length - 1].end_time : null)}</span>
          <span className="meta-chip"><HardDrive size={13} /> {formatFileSize(0)}</span>
          <span className="meta-chip status-chip"><span className="status-dot" /> {transcript?.status ? transcript.status : "Processing"}</span>
        </div>
      </div>

      <div className="workspace-actions">
        {!transcript && canGenerate && <button className="primary-button" type="button" onClick={() => void create()} disabled={busy}>{busy ? "Processing transcript..." : "📝 Generate Transcript"}</button>}
        {transcript && (
          <>
            <button className="secondary-button" type="button" onClick={() => setEditing(current => !current)} disabled={!canEdit || !transcriptReady}><Pencil size={14} />{editing ? "Cancel Edit" : "Edit Transcript"}</button>
            <button className="secondary-button" type="button" onClick={() => void download()} disabled={!transcriptReady}><Download size={14} />{transcriptReady ? "Download Transcript" : "Processing..."}</button>
          </>
        )}
        {transcript?.status === "COMPLETED" && <button className="secondary-button" type="button" onClick={() => void detectKeyMoments()} disabled={busy || !token}><Sparkles size={14} />{keyMoments.length > 0 ? "Redetect Key Moments" : "Detect Key Moments"}</button>}
      </div>
    </header>

    {message && <p className="upload-success" role="status">{message}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}

    <div className="transcript-layout">
      <main className="workspace-main">
        <div className="panel-card player-card">
          <video
            ref={videoRef}
            className="video-player"
            controls
            muted={false}
            preload="auto"
            src={videoUrl}
            onLoadedMetadata={event => {
              console.log("[ClipMind video loaded]", {
                videoId,
                src: event.currentTarget.src,
                duration: event.currentTarget.duration,
                readyState: event.currentTarget.readyState,
              });
            }}
            onError={event => {
              console.error("[Video Error]", {
                videoId,
                mediaUrl: videoUrl,
                error: event.currentTarget.error,
                networkState: event.currentTarget.networkState,
                readyState: event.currentTarget.readyState,
              });
              setError("This video could not be loaded. Check that the uploaded video is available.");
            }}
            onTimeUpdate={event => updatePlaybackTime(event.currentTarget)}
          />
          <div className="player-actions">
            <button className="secondary-button" type="button" onClick={() => void playVideo()}><Video size={14} />Play Video</button>
            <button className="secondary-button" type="button" onClick={() => void download()} disabled={!transcriptReady}><Download size={14} />{transcriptReady ? "Download Transcript" : "Processing..."}</button>
          </div>
        </div>

        <div className="panel-card transcript-content-wrap">
          <div className="transcript-heading-row">
            <div className="transcript-heading"><FileText size={16} /><strong>Transcript</strong></div>
            {transcript?.segments.length ? (
              <label className="transcript-search" aria-label="Search transcript">
                <Search size={14} />
                <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search transcript" />
              </label>
            ) : null}
          </div>

          {!transcript && !busy && (
            <div className="empty-state transcript-empty">
              <div className="empty-icon"><FileText size={18} /></div>
              <h3>No transcript yet</h3>
              <p>Upload and process a video to generate your transcript.</p>
            </div>
          )}

          {busy && (
            <div className="upload-status progress" role="status">
              <span className="status-loader" aria-hidden="true" />
              <div>
                <strong>Processing transcript...</strong>
              </div>
            </div>
          )}

          {transcript && transcript.status !== "COMPLETED" && !busy && (
            <div className="upload-status progress" role="status">
              <span className="status-loader" aria-hidden="true" />
              <div>
                <strong>{transcript.status === "PROCESSING" ? "Processing transcript..." : "Transcript is pending"}</strong>
              </div>
            </div>
          )}

          {transcript?.status === "COMPLETED" && (
            <>
              {editing ? (
                <>
                  <textarea value={draft} onChange={event => setDraft(event.target.value)} rows={12} />
                  <button className="primary-button" type="button" onClick={() => void save()} disabled={busy}>Save transcript</button>
                </>
              ) : (
                <div className="transcript-text">
                  {segments.length > 0 ? segments.map((segment, index) => {
                    const isActive = currentTime >= segment.start_time && currentTime < segment.end_time;
                    return (
                      <div key={`${segment.start_time}-${index}`} className={`transcript-segment ${isActive ? "active" : ""}`}>
                        <time>{formatTime(segment.start_time)}</time>
                        <div className="segment-body">
                          <span className="segment-speaker">Speaker</span>
                          <p>{highlightText(segment.text, normalizedSearch)}</p>
                        </div>
                      </div>
                    );
                  }) : (
                    <div className="empty-state transcript-empty small">
                      <div className="empty-icon"><Search size={18} /></div>
                      <h3>No transcript matches</h3>
                      <p>Try a different search term to find matching transcript content.</p>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </main>

      <aside className="workspace-side">
        <div className="panel-card summary-panel-card">
          <SummaryPanel videoId={videoId} durationSeconds={null} defaultOpen={true} showTrigger={false} />
        </div>

        <div className="panel-card key-moments-panel">
          <div className="transcript-heading"><Sparkles size={16} /><strong>Key Moments</strong></div>
          {keyMoments.length === 0 ? (
            <div className="empty-state transcript-empty small">
              <div className="empty-icon"><Sparkles size={18} /></div>
              <h3>No key moments yet</h3>
              <p>Key moments will appear here after processing.</p>
            </div>
          ) : (
            <div className="key-moment-list">
              {keyMoments.map(moment => {
                const active = currentTime >= moment.start_time && currentTime < moment.end_time;
                return <article key={moment.id} className={`key-moment ${active ? "active" : ""}`}>
                  <div className="key-moment-heading">
                    <span>{formatTime(moment.start_time)} - {formatTime(moment.end_time)}</span>
                    <small>Importance {Math.round(moment.importance_score * 100)}%</small>
                  </div>
                  <strong>{moment.title}</strong>
                  {moment.topic && <small>Topic: {moment.topic}</small>}
                  <p>{moment.description}</p>
                  <button className="secondary-button" type="button" onClick={() => void playMoment(moment)}>
                    <CirclePlay size={14} />Watch Moment
                  </button>
                </article>;
              })}
            </div>
          )}
        </div>
      </aside>
    </div>
  </div>;
}