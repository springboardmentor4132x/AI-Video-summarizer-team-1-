import { useEffect, useState } from "react";
import { FileText, Sparkles, Wand2 } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import {
  generateSummary,
  getKeyMoments,
  getSummary,
  getTranscript,
  retrySummary,
  type KeyMoment,
  type Summary,
  type Transcript,
} from "../../services/api";

interface TranscriptPanelProps {
  videoId: string;
}

function formatTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes.toString().padStart(2, "0")}:${remainder}`;
}

export function TranscriptPanel({ videoId }: TranscriptPanelProps) {
  const { token } = useAuth();
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [keyMoments, setKeyMoments] = useState<KeyMoment[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    getTranscript(token, videoId)
      .then(result => setTranscript(result))
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

  async function createSummary(retry = false) {
    if (!token) return;
    setBusy(true); setError(null); setMessage(retry ? "Retrying summary..." : "Generating summary...");
    try {
      const result = retry ? await retrySummary(token, videoId) : await generateSummary(token, videoId);
      setSummary(result); setMessage(retry ? "Summary retried." : "Summary generated.");
    } catch (reason) {
      setMessage(null); setError(reason instanceof Error ? reason.message : "Summary generation failed.");
    } finally { setBusy(false); }
  }

  const segments = transcript?.segments ?? [];

  return <div className="transcript-panel">
    <div className="transcript-actions">
      {!transcript && <p>Transcript processing has not completed yet.</p>}
      {transcript?.status === "COMPLETED" && <button className="text-button" onClick={() => void createSummary(summary?.status === "FAILED")} disabled={busy || !token || summary?.status === "PROCESSING" || summary?.status === "COMPLETED"}><Wand2 size={14} />{summary?.status === "FAILED" ? "Retry Summary" : summary?.status === "PROCESSING" ? "Summary Processing" : summary?.status === "COMPLETED" ? "Summary Ready" : "Generate Summary"}</button>}
    </div>
    {transcript && transcript.status !== "COMPLETED" && <p className="feature-status">Transcript status: {transcript.status}</p>}
    {message && <p className="upload-success">{message}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {summary && <div className="transcript-content"><div className="transcript-heading"><Wand2 size={16} /><strong>Summary</strong></div><div className="transcript-text"><p>{summary.short_summary}</p><p>{summary.detailed_summary}</p></div></div>}
    {keyMoments.length > 0 && <div className="transcript-content key-moments"><div className="transcript-heading"><Sparkles size={16} /><strong>Key Moments</strong></div>{keyMoments.map(moment => <article className="key-moment" key={moment.id}><div className="key-moment-heading"><strong>{moment.title}</strong><span>{formatTime(moment.start_time)} - {formatTime(moment.end_time)}</span></div><p>{moment.text}</p><small>Importance {Math.round(moment.importance_score * 100)}%</small>{moment.highlight_path && <a className="text-button" href={moment.highlight_path} target="_blank" rel="noreferrer">Download highlight</a>}</article>)}</div>}
    {transcript?.status === "COMPLETED" && <div className="transcript-content"><div className="transcript-heading"><FileText size={16} /><strong>Transcript</strong></div><div className="transcript-text">{segments.length > 0 ? segments.map((segment, index) => <p key={`${segment.start}-${index}`}><time>{formatTime(segment.start)}</time><span>{segment.text}</span></p>) : <p>{transcript.text}</p>}</div></div>}
  </div>;
}