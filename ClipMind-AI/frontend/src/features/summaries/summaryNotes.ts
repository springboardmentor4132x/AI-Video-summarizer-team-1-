import type { Summary } from "../../services/api";

export function buildSummaryNotes(summary: Summary, videoTitle: string): string {
  const shortSummary = (summary.overview || summary.content).trim();
  const longSummary = (summary.content || summary.overview).trim();
  const keyPoints = summary.main_points.map(point => point.trim()).filter(Boolean);
  const keyPointSet = new Set(keyPoints);
  const keyTakeaways = summary.key_takeaways
    .map(takeaway => takeaway.trim())
    .filter(takeaway => takeaway && !keyPointSet.has(takeaway));

  const lines = [
    "ClipMind AI - Video Notes",
    "",
    "Video Title",
    videoTitle.trim() || "Untitled Video",
    "",
    "Short Summary",
    shortSummary,
  ];

  if (longSummary && longSummary !== shortSummary) {
    lines.push("", "Detailed Notes / Long Summary", longSummary);
  }
  if (keyPoints.length > 0) {
    lines.push("", "Key Points", ...keyPoints.map(point => `- ${point}`));
  }
  if (keyTakeaways.length > 0) {
    lines.push("", "Key Takeaways", ...keyTakeaways.map(takeaway => `- ${takeaway}`));
  }

  return `${lines.join("\n").trimEnd()}\n`;
}

function safeFilenameTitle(videoTitle: string): string {
  const withoutExtension = videoTitle.trim().replace(/\.[^./\\]+$/, "");
  const sanitized = withoutExtension
    .replace(/[<>:"/\\|?*\u0000-\u001F]/g, "-")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[. -]+$/g, "");
  const title = sanitized || "video";
  return /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(title) ? `video-${title}` : title;
}

export function downloadSummaryNotes(summary: Summary, videoTitle: string): void {
  const blob = new Blob([buildSummaryNotes(summary, videoTitle)], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${safeFilenameTitle(videoTitle)}-AI-Notes.txt`;
  link.click();
  URL.revokeObjectURL(url);
}