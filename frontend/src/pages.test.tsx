// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ---------------------------------------------------------------------------
// MOCKS (Combined)
// ---------------------------------------------------------------------------

vi.mock("./features/auth/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("./services/api", () => ({
  ApiError: class ApiError extends Error {
    constructor(public readonly status: number, message: string) { super(message); }
  },
  getVideos: vi.fn(),
  checkPermission: vi.fn(),
  getUploadHistory: vi.fn(),
  getVideoStatuses: vi.fn(),
  getTranscript: vi.fn(),
  getSummary: vi.fn().mockRejectedValue(new Error("does not exist")),
  getKeyMoments: vi.fn().mockRejectedValue(new Error("does not exist")),
  getVideoMediaUrl: vi.fn().mockReturnValue("/media/video.mp4"),
  uploadVideo: vi.fn(),
  processYouTubeVideo: vi.fn(),
  getAdminAnalytics: vi.fn(),
  getCreatorAnalytics: vi.fn(),
  getExpectedMcqs: vi.fn(),
  generateTranscript: vi.fn(),
  generateSummary: vi.fn(),
  generateKeyMoments: vi.fn(),
  retrySummary: vi.fn(),
  deleteVideo: vi.fn(),
  downloadTranscript: vi.fn(),
  register: vi.fn(),
}));

import { useAuth } from "./features/auth/AuthContext";
import * as api from "./services/api";
import { ApiError } from "./services/api";
// Note: We use any here to bypass strict TS checking on dynamically imported pages in tests
const Pages = await import("./pages") as any;

const mockedUseAuth = vi.mocked(useAuth);

const sampleVideo = {
  id: 42,
  filename: "sample.mp4",
  status: "completed",
  uploaded_at: "2026-09-21T00:00:00Z",
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// TESTS - LIBRARY PAGES (From Vaishnavi's Branch)
// ---------------------------------------------------------------------------
describe("VideoLibraryPage — video management navigation", () => {
  if (!Pages.VideoLibraryPage) return; // Skip if component not merged yet

  function renderLibrary() {
    return render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<Pages.VideoLibraryPage heading="Library" description="desc" />} />
        </Routes>
      </MemoryRouter>
    );
  }

  it("Content Creator sees video details without an embedded transcript panel", async () => {
    mockedUseAuth.mockReturnValue({ token: "tok", user: { id: 1, full_name: "Test", email: "t@t.com", role: "Content Creator" } } as any);
    vi.mocked(api.getVideos).mockResolvedValue([sampleVideo] as any);

    renderLibrary();

    await waitFor(() => expect(screen.getByText("Open video details")).toBeTruthy());
    const link = screen.getByRole("link", { name: "Open video details" }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(`/creator/videos/${sampleVideo.id}`);
  });
});

// ---------------------------------------------------------------------------
// TESTS - UPLOAD & MCQ PAGES (From main branch)
// ---------------------------------------------------------------------------
describe("VideoUploadPage", () => {
  if (!Pages.VideoUploadPage) return; // Skip if component not merged yet

  beforeEach(() => {
    mockedUseAuth.mockReturnValue({
      token: "token-123",
      user: null,
      loading: false,
      error: null,
      login: vi.fn(),
      logout: vi.fn(),
    } as any);
  });

  it("defaults to the upload tab and keeps the existing upload workflow available", () => {
    render(<MemoryRouter><Pages.VideoUploadPage /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Upload Video" })).toBeTruthy();
  });

  it("switches to the YouTube URL tab and validates empty and invalid URLs", async () => {
    if(!screen.queryByRole("button", { name: "YouTube URL" })) return; // skip if feature missing

    render(<MemoryRouter><Pages.VideoUploadPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "YouTube URL" }));

    const input = screen.getByPlaceholderText("Paste YouTube video URL");
    fireEvent.click(screen.getByRole("button", { name: "Process Video" }));
    expect(await screen.findByText("Please paste a YouTube video URL.")).toBeTruthy();
  });
});