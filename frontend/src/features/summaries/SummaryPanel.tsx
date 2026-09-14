import { useEffect, useState } from "react";
import { Sparkles, X } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { generateSummary, getSummary, retrySummary, type Summary } from "../../services/api";

interface SummaryPanelProps {
  videoId: string;
  durationSeconds: number | null;
  defaultOpen?: boolean;
  showTrigger?: boolean;
}

function formatDuration(seconds: number | null) {
  if (seconds === null) return "Duration pending";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes.toString().padStart(2, "0")}:${remainder}`;
}

export function SummaryPanel({ videoId, durationSeconds, defaultOpen = false, showTrigger = true }: SummaryPanelProps) {
  const { token } = useAuth();
  const [open, setOpen] = useState(defaultOpen);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function openSummary() {
    if (!token) return;
    setOpen(true);
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      setSummary(await getSummary(token, videoId));
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "Summary could not be loaded.";
      if (detail.toLowerCase().includes("does not exist")) setSummary(null);
      else setError(detail);
    } finally {
      setLoading(false);
    }
  }

  async function createSummary() {
    if (!token) return;
    setGenerating(true);
    setError(null);
    setMessage(null);
    try {
      const result = summary?.status === "FAILED" ? await retrySummary(token, videoId) : await generateSummary(token, videoId, Boolean(summary));
      setSummary(result);
      setMessage(summary?.status === "FAILED" ? "Summary retry succeeded." : "Summary generated successfully.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Summary could not be generated.");
    } finally {
      setGenerating(false);
    }
  }

  useEffect(() => {
    if (defaultOpen && token) {
      void openSummary();
    }
  }, [defaultOpen, token, videoId]);

  return <>
    {showTrigger && (
      <button className="text-button summary-action" type="button" onClick={() => void openSummary()}><Sparkles size={14} />AI Summary</button>
    )}
    {open && <div className="summary-panel" role="dialog" aria-label="AI Summary">
      <div className="summary-panel-header"><div className="transcript-heading"><Sparkles size={16} /><strong>AI Summary</strong></div>{showTrigger && <button className="summary-close" type="button" onClick={() => setOpen(false)} aria-label="Close summary"><X size={16} /></button>}</div>
      {loading && <div className="feature-status" role="status"><span className="status-dot" />Loading summary...</div>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {!loading && !error && !summary && <div className="summary-empty"><p>Your AI summary will appear here after processing.</p><button className="primary-button" type="button" onClick={() => void createSummary()} disabled={generating}>{generating ? "Generating summary..." : "Generate summary"}</button></div>}
      {!loading && !error && summary?.status === "FAILED" && <div className="summary-empty"><p>{summary.error_message || "Summary generation failed."}</p><button className="primary-button" type="button" onClick={() => void createSummary()} disabled={generating}>{generating ? "Generating summary..." : "Retry summary"}</button></div>}
      {!loading && !error && summary && summary.status !== "FAILED" && <div className="summary-content"><section><strong>Overview</strong><p>{summary.overview || summary.content}</p></section><section><strong>Main Points</strong><ul>{summary.main_points.map((point, index) => <li key={`${point}-${index}`}>{point}</li>)}</ul></section><section><strong>Key Takeaways</strong><ul>{summary.key_takeaways.map((takeaway, index) => <li key={`${takeaway}-${index}`}>{takeaway}</li>)}</ul></section><section><strong>Duration</strong><p>{formatDuration(summary.duration_seconds ?? durationSeconds)}</p></section></div>}
      {message && <p className="upload-success" role="status">{message}</p>}
    </div>}
  </>;
}