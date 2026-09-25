import { useEffect, useRef, useState } from "react";
import { Download, FileText, Pencil, Search, Sparkles, Wand2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import {
  ApiError,
  downloadTranscript,
  generateKeyMoments,
  generateSummary,
  generateTranscript,
  getKeyMoments,
  getSummary,
  getTranscript,
  getVideoMediaObjectUrl,
  type KeyMoment,
  updateTranscript,
  type Summary,
  type Transcript,
} from "../../services/api";

interface TranscriptPanelProps {
  videoId: string | number;
  filename: string;
  transcriptOnly?: boolean;
  transcriptHref?: string;
}

function formatTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes.toString().padStart(2, "0")}:${remainder}`;
}

function transcriptParagraphs(text: string, maxLength = 520): string[] {
  const sentences = text.match(/[^.!?]+[.!?]+["'”’)]*\s*|[^.!?]+$/g) ?? [];
  const paragraphs: string[] = [];
  let current = "";
  for (const sentence of sentences) {
    const cleanSentence = sentence.trim();
    if (cleanSentence.length > maxLength) {
      if (current.trim()) paragraphs.push(current.trim());
      current = "";
      let wrapped = "";
      for (const word of cleanSentence.split(/\s+/)) {
        if (wrapped && `${wrapped} ${word}`.length > maxLength) {
          paragraphs.push(wrapped);
          wrapped = word;
        } else wrapped = wrapped ? `${wrapped} ${word}` : word;
      }
      if (wrapped) paragraphs.push(wrapped);
      continue;
    }
    const next = current ? `${current.trimEnd()} ${cleanSentence}` : cleanSentence;
    if (current && next.length > maxLength) {
      paragraphs.push(current.trim());
      current = cleanSentence;
    } else current = next;
  }
  if (current.trim()) paragraphs.push(current.trim());
  return paragraphs.length ? paragraphs : (text ? [text] : []);
}

function summaryParagraphs(text: string) {
  const explicit = text.split(/\n\s*\n/).map(paragraph => paragraph.trim()).filter(Boolean);
  return explicit.length > 1 ? explicit : transcriptParagraphs(text, 620);
}

function highlightMatch(text: string, query: string) {
  if (!query.trim()) return text;
  const escaped = query.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return text.split(new RegExp(`(${escaped})`, "gi")).map((part, index) =>
    part.toLowerCase() === query.trim().toLowerCase() ? <mark key={index}>{part}</mark> : part,
  );
}

function waitForVideoMetadata(player: HTMLVideoElement) {
  if (player.readyState >= HTMLMediaElement.HAVE_METADATA) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const onLoaded = () => { cleanup(); resolve(); };
    const onError = () => { cleanup(); reject(new Error("Video metadata could not be loaded.")); };
    const cleanup = () => {
      player.removeEventListener("loadedmetadata", onLoaded);
      player.removeEventListener("error", onError);
    };
    player.addEventListener("loadedmetadata", onLoaded, { once: true });
    player.addEventListener("error", onError, { once: true });
  });
}

export function TranscriptPanel({ videoId, filename, transcriptOnly = false, transcriptHref }: TranscriptPanelProps) {
  const { token, user } = useAuth();
  const videoRef = useRef<HTMLVideoElement>(null);
  const videoRequestRef = useRef<Promise<string> | null>(null);
  const videoObjectUrlRef = useRef<string | null>(null);
  const mediaActiveRef = useRef(false);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [summaryVideoId, setSummaryVideoId] = useState<number | null>(null);
  const [transcriptVideoId, setTranscriptVideoId] = useState<number | null>(null);
  const [summaryRunStatus, setSummaryRunStatus] = useState<Summary["status"] | null>(null);
  const [keyMoments, setKeyMoments] = useState<KeyMoment[]>([]);
  const [transcriptLoading, setTranscriptLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [videoUrl, setVideoUrl] = useState("");
  const canEdit = user?.role === "Content Creator" || user?.role === "Educator" || user?.role === "Administrator";
  const canGenerate = canEdit;
  const currentTranscript = transcriptVideoId === Number(videoId) ? transcript : null;
  const currentSummary = summaryVideoId === Number(videoId)
    && currentTranscript?.id === summary?.transcript_id
    ? summary
    : null;
  const summaryStatus = summaryRunStatus ?? currentSummary?.status ?? "NOT_STARTED";
  useEffect(() => {
    if (transcriptOnly) return;
    mediaActiveRef.current = true;
    setVideoUrl("");
    return () => {
      mediaActiveRef.current = false;
      if (videoObjectUrlRef.current) URL.revokeObjectURL(videoObjectUrlRef.current);
      videoObjectUrlRef.current = null;
      videoRequestRef.current = null;
    };
  }, [filename, token, user?.id, videoId, transcriptOnly]);

  useEffect(() => {
    const player = videoRef.current;
    if (transcriptOnly || !player || !token || !user) return;
    if (typeof IntersectionObserver === "undefined") {
      const bounds = player.getBoundingClientRect();
      if (bounds.bottom >= -120 && bounds.top <= window.innerHeight + 120) {
        void loadVideo(player).catch(() => {
          setError("This video could not be loaded. Check that the uploaded video is available.");
        });
      }
      return;
    }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        observer.disconnect();
        void loadVideo(player).catch(() => {
          setError("This video could not be loaded. Check that the uploaded video is available.");
        });
      }
    }, { rootMargin: "120px" });
    observer.observe(player);
    return () => observer.disconnect();
  }, [filename, token, user?.id, videoId, transcriptOnly]);

  useEffect(() => {
    let active = true;
    const requestedVideoId = Number(videoId);
    setError(null);
    setTranscript(null);
    setSummary(null);
    setTranscriptVideoId(null);
    setSummaryVideoId(null);
    setSummaryRunStatus(null);
    setTranscriptLoading(Boolean(token));
    setSummaryLoading(!transcriptOnly && Boolean(token));
    if (!token) {
      setTranscriptLoading(false);
      setSummaryLoading(false);
      return;
    }
    getTranscript(token, videoId)
      .then(result => {
        if (active) {
          if (result.video_id !== requestedVideoId) {
            setError("The transcript returned does not belong to this video.");
          } else {
            setTranscript(result);
            setTranscriptVideoId(requestedVideoId);
            setDraft(result.text ?? "");
          }
        }
      })
      .catch(reason => {
        if (active && (!(reason instanceof ApiError) || reason.status !== 404)) {
          setError(reason instanceof Error ? reason.message : "Transcript could not be loaded.");
        }
      })
      .finally(() => { if (active) setTranscriptLoading(false); });

    if (!transcriptOnly) getSummary(token, videoId)
      .then(result => {
        if (active) {
          setSummary(result);
          setSummaryVideoId(requestedVideoId);
          setSummaryRunStatus(null);
        }
      })
      .catch(reason => {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 404) {
          setSummary(null);
          setSummaryVideoId(requestedVideoId);
          setSummaryRunStatus("NOT_STARTED");
        } else {
          setError(reason instanceof Error ? reason.message : "Summary could not be loaded.");
        }
      })
      .finally(() => { if (active) setSummaryLoading(false); });

    if (!transcriptOnly) getKeyMoments(token, videoId)
      .then(result => { if (active) setKeyMoments(result.key_moments); })
      .catch(reason => {
        if (active && (!(reason instanceof Error) || !reason.message.toLowerCase().includes("does not exist"))) {
          setError(reason instanceof Error ? reason.message : "Key moments could not be loaded.");
        }
      });
    return () => { active = false; };
  }, [token, videoId, transcriptOnly]);

  async function create() {
    if (!token) return;
    setBusy(true); setError(null); setMessage("Processing transcript...");
    try {
      const result = await generateTranscript(token, videoId);
      setTranscript(result); setDraft(result.text ?? ""); setMessage("Transcript generated.");
    } catch (reason) {
      setMessage(null); setError(reason instanceof Error ? reason.message : "Transcript generation failed.");
    } finally { setBusy(false); }
  }

  async function save() {
    if (!token) return;
    setBusy(true); setError(null);
    try {
      const result = await updateTranscript(token, videoId, draft);
      setTranscript(result); setDraft(result.text ?? ""); setEditing(false); setMessage("Transcript saved successfully.");
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
    setBusy(true); setError(null); setMessage(null); setSummaryRunStatus("PROCESSING");
    try {
      const result = await generateSummary(token, videoId, regenerate);
      setSummary(result); setSummaryRunStatus(null); setMessage(regenerate ? "Summary regenerated." : "Summary generated.");
    } catch (reason) {
      setMessage(null); setSummaryRunStatus("FAILED"); setError(null);
    } finally { setBusy(false); }
  }

  async function detectKeyMoments() {
    if (!token) return;
    setBusy(true); setError(null); setMessage("Detecting key moments...");
    try {
      const result = await generateKeyMoments(token, videoId);
      setKeyMoments(result.key_moments); setMessage("Key moments detected.");
    } catch (reason) {
      setMessage(null); setError(reason instanceof Error ? reason.message : "Key moments could not be detected.");
    } finally { setBusy(false); }
  }

  async function seekToMoment(moment: KeyMoment, play: boolean) {
    const player = videoRef.current;
    if (!player) {
      setError("The video player is not available for this video.");
      return;
    }
    setError(null);
    setMessage(null);
    try {
      await loadVideo(player);
      await waitForVideoMetadata(player);
    } catch {
      setError("This video could not be loaded. Check that the uploaded video is available.");
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
      try {
        await waitForVideoMetadata(player);
        setMessage("The video is loaded at this moment. Press Play in the player to start.");
      } catch {
        setError("This video could not start playback. Check that the video file is available.");
      }
    }
  }

  async function playVideo() {
    const player = videoRef.current;
    if (!player) {
      setError("The video player is not available for this video.");
      return;
    }
    setError(null);
    setMessage(null);
    try {
      await loadVideo(player);
    } catch {
      setError("This video could not be loaded. Check that the uploaded video is available.");
      return;
    }
    try {
      await player.play();
    } catch {
      try {
        await waitForVideoMetadata(player);
        setMessage("The video is loaded and ready. Press Play in the player to start.");
      } catch {
        setError("This video could not start playback. Check that the uploaded video is available.");
      }
    }
  }

  async function loadVideo(player: HTMLVideoElement) {
    if (videoObjectUrlRef.current) return videoObjectUrlRef.current;
    if (!token || !user) throw new Error("Sign in to load this video.");
    if (!videoRequestRef.current) {
      videoRequestRef.current = getVideoMediaObjectUrl(token, videoId, user.id, filename)
        .then(url => {
          if (!mediaActiveRef.current) {
            URL.revokeObjectURL(url);
            throw new Error("The video player is no longer active.");
          }
          videoObjectUrlRef.current = url;
          setVideoUrl(url);
          player.src = url;
          player.load();
          return url;
        })
        .finally(() => { videoRequestRef.current = null; });
    }
    return videoRequestRef.current;
  }

  function updatePlaybackTime(player: HTMLVideoElement) {
    const previousTime = currentTime;
    const nextTime = player.currentTime;
    setCurrentTime(nextTime);
    const endedMoment = keyMoments.some(moment => previousTime >= moment.start_time && previousTime < moment.end_time && nextTime >= moment.end_time);
    if (endedMoment) player.pause();
  }

  const transcriptSegments = currentTranscript?.segments ?? [];
  const readerText = currentTranscript?.text || transcriptSegments.map(segment => segment.text ?? "").join("");
  const paragraphs = transcriptParagraphs(readerText);
  const normalizedSearch = search.trim().toLowerCase();
  const matchingParagraphs = normalizedSearch
    ? paragraphs.filter(paragraph => paragraph.toLowerCase().includes(normalizedSearch))
    : paragraphs;
  const searchMatches = normalizedSearch
    ? readerText.toLowerCase().includes(normalizedSearch)
      ? (matchingParagraphs.length ? matchingParagraphs : paragraphs)
      : []
    : paragraphs;

  return <div className={`transcript-panel${transcriptOnly ? " transcript-only" : ""}`}>
    {transcriptOnly && <><span className="eyebrow">Transcript for</span><h1>{filename}</h1><p className="feature-description">View the timestamped transcript for this video.</p></>}
    {!transcriptOnly && <>
    <video
  ref={videoRef}
  className="video-player"
  controls
  preload="auto"
  {...(videoUrl ? { src: videoUrl } : {})}
  onPointerEnter={event => {
    void loadVideo(event.currentTarget).catch(() => {
      setError("This video could not be loaded. Check that the uploaded video is available.");
    });
  }}
  onFocus={event => {
    void loadVideo(event.currentTarget).catch(() => {
      setError("This video could not be loaded. Check that the uploaded video is available.");
    });
  }}
  onError={() => setError("This video could not be loaded. Check that the uploaded video is available.")}
  onTimeUpdate={event => updatePlaybackTime(event.currentTarget)}
    />
    <button className="text-button play-video-button" type="button" onClick={() => void playVideo()}>▶ Play Video</button>
    </>}
    <div className="transcript-actions">
      {!transcriptOnly && transcriptHref && <Link className="text-button" to={transcriptHref}><FileText size={14} />View Transcript</Link>}
      {!currentTranscript && canGenerate && <button className="text-button" onClick={() => void create()} disabled={busy || transcriptLoading}><Sparkles size={14} />{busy ? "Processing transcript..." : "Generate Transcript"}</button>}
      {currentTranscript?.status === "COMPLETED" && <><button className="text-button" onClick={() => setEditing(current => !current)} disabled={!canEdit}><Pencil size={14} />{editing ? "Cancel Edit" : "Edit Transcript"}</button><button className="text-button" onClick={() => void download()}><Download size={14} />Download Transcript</button></>}
      {!transcriptOnly && currentTranscript?.status === "COMPLETED" && <button className="text-button" onClick={() => void createSummary(summaryStatus === "COMPLETED")} disabled={busy || summaryLoading || summaryStatus === "PROCESSING" || !token}><Wand2 size={14} />{summaryStatus === "COMPLETED" ? "Regenerate Summary" : summaryStatus === "FAILED" ? "Retry Summary" : "Generate Summary"}</button>}
      {!transcriptOnly && currentTranscript?.status === "COMPLETED" && <button className="text-button" onClick={() => void detectKeyMoments()} disabled={busy || !token}><Sparkles size={14} />{keyMoments.length > 0 ? "Redetect Key Moments" : "Detect Key Moments"}</button>}
    </div>
    {message && <p className="upload-success">{message}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    <section className="transcript-content transcript-section" aria-labelledby={`transcript-heading-${videoId}`}>
      <h2 className="transcript-heading"><FileText size={16} /><span id={`transcript-heading-${videoId}`}>Transcript</span><span className={`event-status ${currentTranscript?.status?.toLowerCase() ?? "not-started"}`}>{currentTranscript?.status ?? "NOT_STARTED"}</span></h2>
      {transcriptLoading && <div className="feature-status" role="status"><span className="status-dot" />Loading transcript...</div>}
      {!transcriptLoading && !currentTranscript && <p className="section-hint">Transcript not generated yet.</p>}
      {(currentTranscript?.status === "PROCESSING" || currentTranscript?.status === "PENDING") && <div className="feature-status" role="status"><span className="status-dot" />Transcript is being generated...</div>}
      {currentTranscript?.status === "FAILED" && <div className="notice" role="status"><strong>Transcript unavailable</strong><p>Transcript generation failed. Please try again.</p></div>}
      {currentTranscript?.status === "COMPLETED" && (editing ? <><textarea value={draft} onChange={event => setDraft(event.target.value)} rows={8} /><button className="primary-button" onClick={() => void save()} disabled={busy}>Save transcript</button></> : <><label className="transcript-search"><Search size={14} /><input aria-label="Search transcript" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search transcript" /></label><div className="transcript-text" data-testid="transcript-reader">{searchMatches.length > 0 ? searchMatches.map((paragraph, index) => <p key={index}>{highlightMatch(paragraph, search)}</p>) : <p className="transcript-no-match">No transcript matches found.</p>}</div></>)}
    </section>
    {!transcriptOnly && <section className="transcript-content summary-section" aria-labelledby={`summary-heading-${videoId}`}>
      <h2 className="transcript-heading"><Wand2 size={16} /><span id={`summary-heading-${videoId}`}>Summary</span><span className={`event-status ${summaryStatus.toLowerCase()}`}>{summaryStatus}</span></h2>
      {summaryLoading && <div className="feature-status" role="status"><span className="status-dot" />Loading summary status...</div>}
      {!summaryLoading && summaryStatus === "NOT_STARTED" && <p className="section-hint">Generate a summary to get a quick and detailed view of this transcript.</p>}
      {!summaryLoading && (summaryStatus === "PENDING" || summaryStatus === "PROCESSING") && <div className="feature-status" role="status"><span className="status-dot" />Generating summary...</div>}
      {!summaryLoading && summaryStatus === "FAILED" && <p className="form-error" role="alert">Summary generation failed. Please try again.</p>}
      {!summaryLoading && summaryStatus === "COMPLETED" && currentSummary && <>
        {currentSummary.short_summary && <article className="summary-card summary-card-short"><h3>Short Summary</h3><div className="summary-copy">{summaryParagraphs(currentSummary.short_summary).map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div></article>}
        {currentSummary.detailed_summary && <article className="summary-card summary-card-detailed"><h3>Detailed Summary</h3><div className="summary-copy summary-copy-detailed">{summaryParagraphs(currentSummary.detailed_summary).map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div></article>}
        <small className="summary-meta">Last generated {new Date(currentSummary.updated_at ?? currentSummary.created_at).toLocaleString()}</small>
      </>}
    </section>}
    {!transcriptOnly && keyMoments.length > 0 && <div className="transcript-content key-moments"><div className="transcript-heading"><Sparkles size={16} /><strong>Key Moments</strong></div>{keyMoments.map(moment => { const active = currentTime >= moment.start_time && currentTime < moment.end_time; return <article className={`key-moment${active ? " active" : ""}`} key={moment.id} role="button" tabIndex={0} onClick={() => void seekToMoment(moment, false)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); void seekToMoment(moment, false); } }}><div className="key-moment-heading"><strong>{moment.title}</strong><span>{formatTime(moment.start_time)} - {formatTime(moment.end_time)}</span></div><p>{moment.text}</p><small>{moment.topic ?? "General"} · Importance {Math.round(moment.importance_score * 100)}%</small><button className="text-button key-moment-play" type="button" onClick={event => { event.stopPropagation(); void seekToMoment(moment, true); }}>▶ Play Moment</button></article>; })}</div>}
  </div>;
}
