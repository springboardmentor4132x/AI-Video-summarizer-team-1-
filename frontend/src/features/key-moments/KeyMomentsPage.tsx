import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { generateKeyMoments, getKeyMoments, getVideoMediaObjectUrl, type KeyMoment, type VideoUploadResponse } from "../../services/api";

function formatTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes.toString().padStart(2, "0")}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`;
}

export function KeyMomentsPage() {
  const { videoId } = useParams();
  const { token, user } = useAuth();
  const location = useLocation();
  const video = (location.state as { video?: VideoUploadResponse } | null)?.video;
  const player = useRef<HTMLVideoElement>(null);
  const [moments, setMoments] = useState<KeyMoment[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState("");

  useEffect(() => {
    if (!token || !videoId) return;
    setLoading(true);
    getKeyMoments(token, videoId)
      .then(result => setMoments(Array.isArray(result) ? result : result.key_moments))
      .catch(reason => setError(reason instanceof Error ? reason.message : "Key moments could not be loaded."))
      .finally(() => setLoading(false));
  }, [token, videoId]);

  useEffect(() => {
    if (!token || !user || !video) {
      setVideoUrl("");
      return;
    }
    let active = true;
    let objectUrl: string | null = null;
    setVideoUrl("");
    getVideoMediaObjectUrl(token, video.id, user.id, video.filename)
      .then(url => {
        objectUrl = url;
        if (active) setVideoUrl(url);
        else URL.revokeObjectURL(url);
      })
      .catch(() => {
        if (active) setError("This video could not be loaded. Check that the uploaded video is available.");
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [token, user?.id, video?.filename, video?.id]);

  async function regenerate() {
    if (!token || !videoId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await generateKeyMoments(token, videoId);
      setMoments(Array.isArray(result) ? result : result.key_moments);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Key moments could not be generated.");
    } finally {
      setBusy(false);
    }
  }

  function seek(start: number) {
    if (!Number.isFinite(start) || start < 0 || !player.current) return;
    player.current.currentTime = start;
    try {
      const playback = player.current.play();
      if (playback) void playback.catch(() => undefined);
    } catch {
      return;
    }
  }

  const topics = [...new Set(moments.map(moment => moment.topic).filter((topic): topic is string => Boolean(topic)))];
  if (!videoId || !video) {
    return <section className="simple-page"><span className="eyebrow">Key moments</span><h1>Choose a video from the library</h1><p className="feature-description">Open key moments from a video card to inspect its topics and timestamps.</p><Link className="auth-link" to="/creator/videos">Back to video library</Link></section>;
  }

  return <section className="simple-page key-moments-page">
    <span className="eyebrow">Module 3 · {video.filename}</span>
    <h1>Topics and key moments</h1>
    <p className="feature-description">Semantic topic regions and ranked moments from the stored transcript.</p>
    <video ref={player} className="video-player" controls preload="metadata" {...(videoUrl ? { src: videoUrl } : {})} />
    <div className="transcript-actions"><button className="primary-button" type="button" onClick={() => void regenerate()} disabled={busy}>{busy ? "Detecting..." : "Regenerate key moments"}</button></div>
    {loading && <div className="feature-status" role="status"><span className="status-dot" />Loading key moments...</div>}
    {error && <div className="notice" role="alert">{error}</div>}
    {!loading && !error && moments.length === 0 && <div className="feature-placeholder"><Sparkles size={18} /><h2>No key moments yet</h2><p>Generate moments after the transcript has completed.</p></div>}
    {!loading && !error && moments.length > 0 && <>
      <div className="feature-placeholder"><span className="eyebrow">Topics</span><div className="transcript-actions">{topics.map(topic => <button className="text-button" type="button" key={topic} onClick={() => { const first = moments.find(moment => moment.topic === topic); if (first) seek(first.start_time); }}>{topic}</button>)}</div></div>
      <div className="key-moments">{moments.map(moment => <article className="key-moment" key={moment.id}><button className="text-button" type="button" onClick={() => seek(moment.start_time)}><strong>{formatTime(moment.start_time)} · {moment.title}</strong></button><p>{moment.text}</p><small>{moment.topic ?? "General"} · {formatTime(moment.start_time)} - {formatTime(moment.end_time)} · Importance {Math.round(moment.importance_score * 100)}%</small></article>)}</div>
    </>}
  </section>;
}
