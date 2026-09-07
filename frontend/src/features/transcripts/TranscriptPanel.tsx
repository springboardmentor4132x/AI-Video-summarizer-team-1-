import { useEffect, useRef, useState } from "react";
import { Download, FileText, Pencil, Search, Sparkles, Wand2 } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import {
  downloadTranscript,
  generateKeyMoments,
  generateSummary,
  generateTranscript,
  getKeyMoments,
  getSummary,
  getTranscript,
  getVideoMediaUrl,
  type KeyMoment,
  updateTranscript,
  type Summary,
  type Transcript,
} from "../../services/api";

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

export function TranscriptPanel({ videoId, ownerId, filename }: TranscriptPanelProps) {
  const { token, user } = useAuth();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
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
  const videoUrl = getVideoMediaUrl(videoId, ownerId, filename);

  console.log("[ClipMind video URL]", {
  videoId,
  ownerId,
  filename,
  videoUrl,
});

  useEffect(() => {
    if (!token) return;
    getTranscript(token, videoId)
      .then(result => { setTranscript(result); setDraft(result.text); })
      .catch(reason => {
        if (!(reason instanceof Error) || !reason.message.toLowerCase().includes("does not exist")) {
          setError(reason instanceof Error ? reason.message : "Transcript could not be loaded.");
        }
      });

    getSummary(token, videoId)
      .then(setSummary)
      .catch(reason => {
        if (!(reason instanceof Error) || !reason.message.toLowerCase().includes("does not exist")) {
          setError(reason instanceof Error ? reason.message : "Summary could not be loaded.");
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
    if (!token) return;
    try {
      const blob = await downloadTranscript(token, videoId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = "transcript.txt"; link.click(); URL.revokeObjectURL(url);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Transcript download failed."); }
  }

  async function createSummary(regenerate = false) {
    if (!token) return;
    setBusy(true); setError(null); setMessage(regenerate ? "Regenerating summary..." : "Generating summary...");
    try {
      const result = await generateSummary(token, videoId, regenerate);
      setSummary(result); setMessage(regenerate ? "Summary regenerated." : "Summary generated.");
    } catch (reason) {
      setMessage(null); setError(reason instanceof Error ? reason.message : "Summary generation failed.");
    } finally { setBusy(false); }
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

  async function seekToMoment(moment: KeyMoment, play: boolean) {
    const player = videoRef.current;
    console.log("[ClipMind playback] Play Moment", {
      videoId,
      keyMomentId: moment.id,
      startTime: moment.start_time,
      videoUrl,
      videoRefExists: Boolean(player),
      readyState: player?.readyState ?? null,
    });
    if (!player) {
      setError("The video player is not available for this video.");
      return;
    }
    player.currentTime = moment.start_time;
    if (!play) {
      player.pause();
      return;
    }
    try {
      await player.play();
    } catch {
      setError("This video could not start playback. Check that the video file is available.");
    }
  }

  async function playVideo() {
    const player = videoRef.current;
    console.log("[ClipMind playback] Play Video", {
      videoId,
      videoUrl,
      videoRefExists: Boolean(player),
      readyState: player?.readyState ?? null,
    });
    if (!player) {
      setError("The video player is not available for this video.");
      return;
    }
    try {
      await player.play();
    } catch {
      setError("This video could not start playback. Check that the uploaded video is available.");
    }
  }

  function updatePlaybackTime(player: HTMLVideoElement) {
    const previousTime = currentTime;
    const nextTime = player.currentTime;
    setCurrentTime(nextTime);
    const endedMoment = keyMoments.some(moment => previousTime >= moment.start_time && previousTime < moment.end_time && nextTime >= moment.end_time);
    if (endedMoment) player.pause();
  }

  const normalizedSearch = search.trim().toLowerCase();
  const segments = transcript?.segments.filter(segment => !normalizedSearch || segment.text.toLowerCase().includes(normalizedSearch)) ?? [];

  return <div className="transcript-panel">
    <video
  ref={videoRef}
  className="video-player"
  controls
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
    console.error("[ClipMind video error]", {
      videoId,
      src: event.currentTarget.src,
      error: event.currentTarget.error,
      networkState: event.currentTarget.networkState,
      readyState: event.currentTarget.readyState,
    });
    setError("This video could not be loaded. Check that the uploaded video is available.");
  }}
  onTimeUpdate={event => updatePlaybackTime(event.currentTarget)}
/>
    <button className="text-button play-video-button" type="button" onClick={() => void playVideo()}>▶ Play Video</button>
    <div className="transcript-actions">
      {!transcript && canGenerate && <button className="text-button" onClick={() => void create()} disabled={busy}><Sparkles size={14} />{busy ? "Processing transcript..." : "Generate Transcript"}</button>}
      {transcript?.status === "COMPLETED" && <><button className="text-button" onClick={() => setEditing(current => !current)} disabled={!canEdit}><Pencil size={14} />{editing ? "Cancel Edit" : "Edit Transcript"}</button><button className="text-button" onClick={() => void download()}><Download size={14} />Download Transcript</button></>}
      {transcript?.status === "COMPLETED" && <button className="text-button" onClick={() => void createSummary(Boolean(summary))} disabled={busy || !token}><Wand2 size={14} />{summary ? "Regenerate Summary" : "Generate Summary"}</button>}
      {transcript?.status === "COMPLETED" && <button className="text-button" onClick={() => void detectKeyMoments()} disabled={busy || !token}><Sparkles size={14} />{keyMoments.length > 0 ? "Redetect Key Moments" : "Detect Key Moments"}</button>}
    </div>
    {message && <p className="upload-success">{message}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {summary && <div className="transcript-content"><div className="transcript-heading"><Wand2 size={16} /><strong>Summary</strong></div><div className="transcript-text"><p>{summary.content}</p></div></div>}
    {keyMoments.length > 0 && <div className="transcript-content key-moments"><div className="transcript-heading"><Sparkles size={16} /><strong>Key Moments</strong></div>{keyMoments.map(moment => { const active = currentTime >= moment.start_time && currentTime < moment.end_time; return <article className={`key-moment${active ? " active" : ""}`} key={moment.id} role="button" tabIndex={0} onClick={() => void seekToMoment(moment, false)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); void seekToMoment(moment, false); } }}><div className="key-moment-heading"><strong>{moment.title}</strong><span>{formatTime(moment.start_time)} - {formatTime(moment.end_time)}</span></div><p>{moment.description}</p><small>Importance {Math.round(moment.importance_score * 100)}%</small><button className="text-button key-moment-play" type="button" onClick={event => { event.stopPropagation(); void seekToMoment(moment, true); }}>▶ Play Moment</button></article>; })}</div>}
    {transcript?.status === "COMPLETED" && <div className="transcript-content"><div className="transcript-heading"><FileText size={16} /><strong>Transcript</strong></div>{editing ? <><textarea value={draft} onChange={event => setDraft(event.target.value)} rows={8} /><button className="primary-button" onClick={() => void save()} disabled={busy}>Save transcript</button></> : <>{transcript.segments.length > 0 && <label className="transcript-search"><Search size={14} /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search transcript" /></label>}<div className="transcript-text">{segments.length > 0 ? segments.map((segment, index) => <p key={`${segment.start_time}-${index}`}><time>{formatTime(segment.start_time)}</time><span>{segment.text}</span></p>) : <p>{transcript.text}</p>}</div></>}</div>}
  </div>;
}