// @vitest-environment jsdom
/**
 * Tests for purpose-separated video and transcript navigation.
 *
 * Each test renders into a fresh container and cleans up afterwards to
 * avoid cross-test DOM contamination.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

// ---------------------------------------------------------------------------
// All external dependencies are hoisted and mocked at module level.
// Individual tests control user.role by swapping the AuthContext mock return.
// ---------------------------------------------------------------------------

const mockGetVideos = vi.fn();
const mockGetTranscript = vi.fn();
const mockCheckPermission = vi.fn();
let mockUserRole = "Content Creator";
let mockUserId = 1;

vi.mock("./features/auth/AuthContext", () => ({
  useAuth: () => ({
    token: "tok",
    user: { id: mockUserId, name: "Test", email: "t@t.com", role: mockUserRole, created_at: "" },
  }),
}));

vi.mock("./services/api", () => ({
  ApiError: class ApiError extends Error {
    constructor(public readonly status: number, message: string) { super(message); }
  },
  getVideos: (...args: unknown[]) => mockGetVideos(...args),
  checkPermission: (...args: unknown[]) => mockCheckPermission(...args),
  getUploadHistory: vi.fn(),
  getVideoStatuses: vi.fn(),
  getTranscript: (...args: unknown[]) => mockGetTranscript(...args),
  getSummary: vi.fn().mockRejectedValue(new Error("does not exist")),
  getKeyMoments: vi.fn().mockRejectedValue(new Error("does not exist")),
  getVideoMediaUrl: () => "/media/video.mp4",
}));

const sampleVideo = {
  id: 42,
  filename: "sample.mp4",
  status: "completed",
  uploaded_at: "2026-09-21T00:00:00Z",
};

// ---------------------------------------------------------------------------
// Import component AFTER mocks are set up
// ---------------------------------------------------------------------------

import { RoleFeaturePage, TranscriptLibraryPage, VideoLibraryPage } from "./pages";
import { ApiError } from "./services/api";

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function renderLibrary() {
  return render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<VideoLibraryPage heading="Library" description="desc" />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("VideoLibraryPage — video management navigation", () => {
  it("Content Creator sees video details without an embedded transcript panel", async () => {
    mockUserRole = "Content Creator";
    mockUserId = 1;
    mockGetVideos.mockResolvedValue([sampleVideo]);

    renderLibrary();

    await waitFor(() => expect(screen.getByText("Open video details")).toBeTruthy());
    const link = screen.getByRole("link", { name: "Open video details" }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(`/creator/videos/${sampleVideo.id}`);
    expect(screen.queryByRole("region", { name: "Transcript" })).toBeNull();
  });

  it("Learner link points to learner video details", async () => {
    mockUserRole = "Learner";
    mockUserId = 2;
    mockGetVideos.mockResolvedValue([sampleVideo]);

    renderLibrary();

    await waitFor(() => expect(screen.getByText("Open video details")).toBeTruthy());
    const link = screen.getByRole("link", { name: "Open video details" }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(`/learner/videos/${sampleVideo.id}`);
  });

  it("Educator link points to educator video details", async () => {
    mockUserRole = "Educator";
    mockUserId = 3;
    mockGetVideos.mockResolvedValue([sampleVideo]);

    renderLibrary();

    await waitFor(() => expect(screen.getByText("Open video details")).toBeTruthy());
    const link = screen.getByRole("link", { name: "Open video details" }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(`/educator/videos/${sampleVideo.id}`);
  });

  it("Administrator has no key-moments link", async () => {
    mockUserRole = "Administrator";
    mockUserId = 4;
    mockGetVideos.mockResolvedValue([sampleVideo]);

    renderLibrary();

    await waitFor(() => expect(screen.getByText("sample.mp4")).toBeTruthy());
    expect(screen.queryByRole("link", { name: "Open video details" })).toBeNull();
  });
});

describe("TranscriptLibraryPage", () => {
  it("shows each video transcript status and links to that video's transcript", async () => {
    mockUserRole = "Content Creator";
    mockGetVideos.mockResolvedValue([sampleVideo]);
    mockGetTranscript.mockResolvedValue({ id: 9, video_id: 42, status: "COMPLETED", text: "River lesson", segments: [{ start: 0, end: 2, text: "River lesson" }], created_at: "2026-09-21T00:00:00Z", updated_at: "2026-09-21T01:00:00Z" });
    render(<MemoryRouter><TranscriptLibraryPage heading="Transcripts" description="desc" /></MemoryRouter>);
    expect(await screen.findByText("COMPLETED")).toBeTruthy();
    expect(screen.getByText("Available")).toBeTruthy();
    expect((screen.getByRole("link", { name: "View Transcript" }) as HTMLAnchorElement).getAttribute("href")).toBe("/creator/transcripts/42");
  });
});

describe("RoleFeaturePage", () => {
  it("reports missing backend modules as not implemented instead of ready", async () => {
    mockCheckPermission.mockRejectedValueOnce(new ApiError(404, "Not Found"));
    render(<MemoryRouter><RoleFeaturePage title="Users" description="Manage accounts" endpoint="/rbac/admin/users" /></MemoryRouter>);

    expect(await screen.findByText("This feature is not implemented yet.")).toBeTruthy();
    expect(screen.getByText("Not implemented")).toBeTruthy();
    expect(screen.queryByText("Module ready")).toBeNull();
  });
});
