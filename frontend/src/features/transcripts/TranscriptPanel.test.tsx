// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TranscriptPanel } from "./TranscriptPanel";
import { ApiError } from "../../services/api";

const api = vi.hoisted(() => ({
  getTranscript: vi.fn(),
  getSummary: vi.fn(),
  getKeyMoments: vi.fn(),
  generateSummary: vi.fn(),
  generateKeyMoments: vi.fn(),
  generateTranscript: vi.fn(),
  updateTranscript: vi.fn(),
  downloadTranscript: vi.fn(),
  getVideoMediaObjectUrl: vi.fn(),
}));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ token: "test-token", user: { id: 7, role: "Content Creator" } }),
}));

vi.mock("../../services/api", async importOriginal => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return { ...actual, ...api };
});

const transcript = {
  id: 3,
  video_id: 4,
  text: "The transcript contains the full spoken lesson.",
  segments: [{ start: 0, end: 4, text: "The transcript contains the full spoken lesson." }],
  language: "en",
  status: "COMPLETED" as const,
  created_at: "2026-09-21T10:00:00Z",
  updated_at: "2026-09-21T10:01:00Z",
};

const completedSummary = {
  id: 5,
  transcript_id: 3,
  short_summary: "The lesson explains how AI agents use tools and context.",
  detailed_summary: "The lesson describes agent tools, shared context, retrieval, and memory, then compares how each supports reliable task completion.",
  status: "COMPLETED" as const,
  created_at: "2026-09-21T10:02:00Z",
  updated_at: "2026-09-21T10:04:00Z",
};

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  api.getTranscript.mockResolvedValue(transcript);
  api.getSummary.mockResolvedValue(completedSummary);
  api.getKeyMoments.mockResolvedValue({ video_id: 4, status: "completed", key_moments: [] });
  api.generateSummary.mockResolvedValue(completedSummary);
});

describe("TranscriptPanel summary presentation", () => {
  it("shows distinct short and detailed sections with the last generated time", async () => {
    render(<TranscriptPanel videoId={4} filename="lesson.mp4" />);

    expect(await screen.findByRole("heading", { name: "Short Summary" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Detailed Summary" })).toBeTruthy();
    expect(screen.getByText(completedSummary.short_summary)).toBeTruthy();
    expect(screen.getByText(completedSummary.detailed_summary)).toBeTruthy();
    expect(screen.getByText(/Last generated/)).toBeTruthy();
    expect(screen.getByRole("region", { name: "Transcript" })).toBeTruthy();
    expect(screen.queryByText("00:00")).toBeNull();
    expect(screen.getByTestId("transcript-reader").textContent).toContain(transcript.text);
  });

  it("searches transcript text and highlights matches without timestamps", async () => {
    const source = "The first sentence introduces rivers. The second sentence explains tributaries. A final sentence explains deltas.";
    api.getTranscript.mockResolvedValue({ ...transcript, text: source, segments: [
      { start: 0, end: 2, text: "The first sentence introduces rivers." },
      { start: 2, end: 4, text: "The second sentence explains tributaries. A final sentence explains deltas." },
    ] });
    render(<TranscriptPanel videoId={4} filename="lesson.mp4" transcriptOnly />);
    const search = await screen.findByRole("textbox", { name: "Search transcript" });
    fireEvent.change(search, { target: { value: "tributaries" } });
    expect(screen.getByTestId("transcript-reader").textContent).toContain("tributaries");
    expect(screen.getByTestId("transcript-reader").querySelector("mark")?.textContent).toBe("tributaries");
    expect(screen.queryByText(/\d{2}:\d{2}/)).toBeNull();
  });

  it("groups adjacent Whisper segments into readable paragraphs", async () => {
    const sentences = Array.from({ length: 18 }, (_, index) => `Sentence ${index + 1} explains a meaningful detail about the same lesson topic.`);
    const source = sentences.join(" ");
    api.getTranscript.mockResolvedValue({ ...transcript, text: source, segments: sentences.map((text, index) => ({ start: index * 2, end: index * 2 + 2, text })) });
    render(<TranscriptPanel videoId={4} filename="lesson.mp4" transcriptOnly />);
    const reader = await screen.findByTestId("transcript-reader");
    expect(reader.querySelectorAll("p").length).toBeGreaterThan(1);
    expect(reader.querySelectorAll("p").length).toBeLessThan(sentences.length);
    expect(Array.from(reader.querySelectorAll("p"), paragraph => paragraph.textContent).join(" ")).toBe(source);
  });

  it("shows processing status without rendering empty summary boxes", async () => {
    api.getSummary.mockResolvedValue({ ...completedSummary, status: "PROCESSING" });
    render(<TranscriptPanel videoId={4} filename="lesson.mp4" />);

    expect(await screen.findByText("Generating summary...")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Short Summary" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Detailed Summary" })).toBeNull();
  });

  it("reports generation failure and leaves a retry action", async () => {
    api.getSummary.mockResolvedValue({ ...completedSummary, short_summary: null, detailed_summary: null, status: "NOT_STARTED" });
    api.generateSummary.mockRejectedValue(new Error("backend details"));
    render(<TranscriptPanel videoId={4} filename="lesson.mp4" />);

    fireEvent.click(await screen.findByRole("button", { name: "Generate Summary" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Summary generation failed. Please try again.");
    expect(screen.getByRole("button", { name: "Retry Summary" })).toBeTruthy();
  });

  it("does not show Video A summary when Video B loads before A's response", async () => {
    let resolveTranscriptA!: (value: typeof transcript) => void;
    let resolveSummaryA!: (value: typeof completedSummary) => void;
    api.getTranscript.mockReturnValueOnce(new Promise(resolve => { resolveTranscriptA = resolve; }));
    api.getSummary.mockReturnValueOnce(new Promise(resolve => { resolveSummaryA = resolve; }));

    const view = render(<TranscriptPanel videoId={4} filename="video-a.mp4" />);
    api.getTranscript.mockResolvedValueOnce({ ...transcript, id: 8, video_id: 5, text: "Video B transcript: DevOps roadmap and Linux." });
    api.getSummary.mockResolvedValueOnce({ ...completedSummary, id: 9, transcript_id: 8, short_summary: "Video B summary: DevOps roadmap and Linux.", detailed_summary: "Video B explains a DevOps roadmap and Linux skills." });
    view.rerender(<TranscriptPanel videoId={5} filename="video-b.mp4" />);

    expect(await screen.findByText("Video B summary: DevOps roadmap and Linux.")).toBeTruthy();
    await act(async () => {
      resolveTranscriptA({ ...transcript, text: "Video A transcript: Indian rivers and tributaries." });
      resolveSummaryA({ ...completedSummary, short_summary: "Video A summary: Indian rivers and tributaries.", detailed_summary: "Video A explains Indian rivers and their tributaries." });
    });

    expect(screen.getByText("Video B summary: DevOps roadmap and Linux.")).toBeTruthy();
    expect(screen.queryByText("Video A summary: Indian rivers and tributaries.")).toBeNull();
  });

  it("shows processing state for a pending transcript", async () => {
    api.getTranscript.mockResolvedValue({ ...transcript, status: "PENDING" });
    render(<TranscriptPanel videoId={4} filename="lesson.mp4" transcriptOnly />);
    expect(await screen.findByText("Transcript is being generated...")).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "Search transcript" })).toBeNull();
  });

  it("shows failed state without presenting empty transcript text as completed", async () => {
    api.getTranscript.mockResolvedValue({ ...transcript, status: "FAILED", text: null, segments: null });
    render(<TranscriptPanel videoId={4} filename="lesson.mp4" transcriptOnly />);
    expect(await screen.findByText("Transcript generation failed. Please try again.")).toBeTruthy();
    expect(screen.queryByText("Transcript text unavailable.")).toBeNull();
  });

  it("shows a not-started state for a missing transcript", async () => {
    api.getTranscript.mockRejectedValue(new ApiError(404, "not found"));
    render(<TranscriptPanel videoId={4} filename="lesson.mp4" transcriptOnly />);
    expect(await screen.findByText("Transcript not generated yet.")).toBeTruthy();
  });

  it("keeps edit/save bound to the selected video's transcript", async () => {
    api.updateTranscript.mockResolvedValue({ ...transcript, text: "Updated river transcript." });
    render(<TranscriptPanel videoId={4} filename="lesson.mp4" transcriptOnly />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Transcript" }));
    const editor = await screen.findByRole("textbox");
    fireEvent.change(editor, { target: { value: "Updated river transcript." } });
    fireEvent.click(screen.getByRole("button", { name: "Save transcript" }));
    expect(await screen.findByText("Updated river transcript.")).toBeTruthy();
    expect(api.updateTranscript).toHaveBeenCalledWith("test-token", 4, "Updated river transcript.");
  });

  it("downloads only the selected video's transcript", async () => {
    api.downloadTranscript.mockResolvedValue(new Blob(["river transcript"]));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const objectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:test-transcript");
    const revokeUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    render(<TranscriptPanel videoId={4} filename="lesson.mp4" transcriptOnly />);
    fireEvent.click(await screen.findByRole("button", { name: "Download Transcript" }));
    await screen.findByRole("region", { name: "Transcript" });
    expect(api.downloadTranscript).toHaveBeenCalledWith("test-token", 4);
    expect(click).toHaveBeenCalled();
    objectUrl.mockRestore();
    revokeUrl.mockRestore();
    click.mockRestore();
  });
});
