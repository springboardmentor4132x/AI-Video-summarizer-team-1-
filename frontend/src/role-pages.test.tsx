// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockGetLearningHistory = vi.fn();
const mockGetLearningBookmarks = vi.fn();
const mockGetVideos = vi.fn();
const mockDeleteLearningBookmark = vi.fn();

vi.mock("./features/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: 9, role: "Learner", full_name: "Learner", email: "learner@example.com" }, token: "test-token" }) }));
vi.mock("./services/api", async importOriginal => {
  const actual = await importOriginal<typeof import("./services/api")>();
  return { ...actual, getLearningHistory: (...args: unknown[]) => mockGetLearningHistory(...args), getLearningBookmarks: (...args: unknown[]) => mockGetLearningBookmarks(...args), getVideos: (...args: unknown[]) => mockGetVideos(...args), deleteLearningBookmark: (...args: unknown[]) => mockDeleteLearningBookmark(...args) };
});

import { AdminReportsPage, LearnerBookmarksPage, LearnerHistoryPage } from "./role-pages";

afterEach(() => cleanup());

describe("learner role pages", () => {
  it("loads saved learning history and offers a resume link with its position", async () => {
    mockGetLearningHistory.mockResolvedValue([{ id: 1, video_id: 12, last_position_seconds: 72, viewed_at: "2026-10-05T00:00:00Z" }]);
    mockGetVideos.mockResolvedValue([{ id: "12", filename: "lecture.mp4" }]);
    render(<MemoryRouter><LearnerHistoryPage /></MemoryRouter>);
    expect(await screen.findByText("lecture.mp4")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Continue" }).getAttribute("href")).toContain("videoId=12&position=72");
  });

  it("removes a persisted bookmark from the learner list", async () => {
    mockGetLearningBookmarks.mockResolvedValue([{ id: 3, video_id: 12, key_moment_id: null, kind: "summary", note: "Saved", created_at: "2026-10-05T00:00:00Z" }]);
    mockGetVideos.mockResolvedValue([{ id: "12", filename: "lecture.mp4" }]);
    mockDeleteLearningBookmark.mockResolvedValue(undefined);
    render(<MemoryRouter><LearnerBookmarksPage /></MemoryRouter>);
    expect(await screen.findByText("lecture.mp4")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(mockDeleteLearningBookmark).toHaveBeenCalledWith("test-token", 3));
    expect(screen.queryByText("lecture.mp4")).toBeNull();
  });
});

describe("administrator reports", () => {
  it("loads protected report metrics and recent content from the reports API", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      overview: { total_users: 4, total_videos: 2, completed_videos: 1, processing_videos: 1, failed_videos: 0, total_transcripts: 1, total_summaries: 1, total_key_moments: 3 },
      summary_reports: { completed_summaries: 1, total_summary_words: 30, average_summary_words: 30, generation_rate_percentage: 50 },
      usage: { users_by_role: [{ label: "Educator", count: 1 }] },
      recent_videos: [{ id: "2", filename: "class.mp4", owner_name: "Teacher", status: "completed", uploaded_at: "2026-10-05T00:00:00Z", summary_word_count: 30, key_moment_count: 3 }],
    }) });
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter><AdminReportsPage /></MemoryRouter>);
    expect(await screen.findByText("class.mp4")).toBeTruthy();
    expect(screen.getByText("4")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/admin/reports"), expect.objectContaining({ headers: { Authorization: "Bearer test-token" } }));
  });
});
