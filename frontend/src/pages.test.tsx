// @vitest-environment jsdom
/**
 * Tests for VideoLibraryPage — verifies that the "Open key moments" link
 * targets the correct role-specific route for each supported role, and is
 * absent for the Administrator role which has no key-moments route.
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
let mockUserRole = "Content Creator";
let mockUserId = 1;

vi.mock("./features/auth/AuthContext", () => ({
  useAuth: () => ({
    token: "tok",
    user: { id: mockUserId, name: "Test", email: "t@t.com", role: mockUserRole, created_at: "" },
  }),
}));

vi.mock("./services/api", () => ({
  getVideos: (...args: unknown[]) => mockGetVideos(...args),
  checkPermission: vi.fn(),
  getUploadHistory: vi.fn(),
  getVideoStatuses: vi.fn(),
  getTranscript: vi.fn().mockRejectedValue(new Error("does not exist")),
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

import { VideoLibraryPage } from "./pages";

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

describe("VideoLibraryPage — key-moments link routing", () => {
  it("Content Creator link points to /creator/key-moments/:id", async () => {
    mockUserRole = "Content Creator";
    mockUserId = 1;
    mockGetVideos.mockResolvedValue([sampleVideo]);

    renderLibrary();

    await waitFor(() => expect(screen.getByText("Open key moments")).toBeTruthy());
    const link = screen.getByRole("link", { name: "Open key moments" }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(`/creator/key-moments/${sampleVideo.id}`);
  });

  it("Learner link points to /learner/key-moments/:id", async () => {
    mockUserRole = "Learner";
    mockUserId = 2;
    mockGetVideos.mockResolvedValue([sampleVideo]);

    renderLibrary();

    await waitFor(() => expect(screen.getByText("Open key moments")).toBeTruthy());
    const link = screen.getByRole("link", { name: "Open key moments" }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(`/learner/key-moments/${sampleVideo.id}`);
  });

  it("Educator link points to /educator/key-moments/:id", async () => {
    mockUserRole = "Educator";
    mockUserId = 3;
    mockGetVideos.mockResolvedValue([sampleVideo]);

    renderLibrary();

    await waitFor(() => expect(screen.getByText("Open key moments")).toBeTruthy());
    const link = screen.getByRole("link", { name: "Open key moments" }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(`/educator/key-moments/${sampleVideo.id}`);
  });

  it("Administrator has no key-moments link", async () => {
    mockUserRole = "Administrator";
    mockUserId = 4;
    mockGetVideos.mockResolvedValue([sampleVideo]);

    renderLibrary();

    await waitFor(() => expect(screen.getByText("sample.mp4")).toBeTruthy());
    expect(screen.queryByRole("link", { name: "Open key moments" })).toBeNull();
  });
});
