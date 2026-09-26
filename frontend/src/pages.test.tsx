// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MCQQuizPage, RoleFeaturePage, VideoUploadPage } from "./pages";
import { useAuth } from "./features/auth/AuthContext";

vi.mock("./features/auth/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("./services/api", () => ({
  ApiError: class ApiError extends Error {
    constructor(public readonly status: number, message: string) { super(message); }
  },
  uploadVideo: vi.fn(),
  processYouTubeVideo: vi.fn(),
  getAdminAnalytics: vi.fn(),
  getCreatorAnalytics: vi.fn(),
  getVideoStatuses: vi.fn(),
  getVideos: vi.fn(),
  getUploadHistory: vi.fn(),
  getTranscript: vi.fn(),
  getSummary: vi.fn(),
  getKeyMoments: vi.fn(),
  getExpectedMcqs: vi.fn(),
  generateTranscript: vi.fn(),
  generateSummary: vi.fn(),
  generateKeyMoments: vi.fn(),
  retrySummary: vi.fn(),
  deleteVideo: vi.fn(),
  downloadTranscript: vi.fn(),
  downloadSummary: vi.fn(),
  register: vi.fn(),
  checkPermission: vi.fn(),
  getVideoMediaUrl: vi.fn(),
}));

const mockedUseAuth = vi.mocked(useAuth);
const api = await import("./services/api");
const mockedUploadVideo = vi.mocked(api.uploadVideo);

describe("VideoUploadPage", () => {
  beforeEach(() => {
    mockedUseAuth.mockReturnValue({
      token: "token-123",
      user: null,
      loading: false,
      error: null,
      login: vi.fn(),
      logout: vi.fn(),
    } as any);
    mockedUploadVideo.mockReset();
  });

  it("defaults to the upload tab and keeps the existing upload workflow available", () => {
    render(<VideoUploadPage />);
    expect(screen.getByRole("button", { name: "Upload Video" })).toHaveClass("primary-button");
    expect(screen.getByLabelText(/choose a video file|Drop your video here/i)).toBeInTheDocument();
  });

  it("clearly disables YouTube URL processing because no backend endpoint exists", () => {
    render(<VideoUploadPage />);
    expect(screen.getByRole("button", { name: /YouTube URL \(unavailable\)/i })).toBeDisabled();
    expect(screen.getByText(/backend does not support it/i)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Paste YouTube video URL")).not.toBeInTheDocument();
  });

  it("shows completed videos but clearly marks quiz generation unavailable without a backend endpoint", async () => {
    mockedUseAuth.mockReturnValue({
      token: "token-123",
      user: {
        id: "user-1",
        email: "creator@example.com",
        full_name: "Creator User",
        role: "Content Creator",
      },
      loading: false,
      error: null,
      login: vi.fn(),
      logout: vi.fn(),
    } as any);

    vi.mocked(api.getVideos).mockResolvedValue([
      {
        id: "video-1",
        filename: "sample.mp4",
        mime_type: "video/mp4",
        file_size_bytes: 1024,
        duration_seconds: 120,
        processing_status: "COMPLETED",
        source_type: "UPLOAD",
        uploaded_at: "2024-01-01T00:00:00Z",
        owner_id: "user-1",
        owner_name: "Creator User",
      },
    ]);
    render(<MCQQuizPage />);

    await waitFor(() => expect(api.getVideos).toHaveBeenCalledWith("token-123", 500));
    fireEvent.change(screen.getByLabelText(/Select Video/i), { target: { value: "video-1" } });
    expect(screen.getByRole("option", { name: "sample.mp4" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Generate Quiz \(unavailable\)/i })).toBeDisabled();
    expect(screen.getByText(/backend does not currently provide an MCQ endpoint/i)).toBeInTheDocument();
    expect(api.getExpectedMcqs).not.toHaveBeenCalled();
  });
});

describe("RoleFeaturePage", () => {
  it("keeps unavailable role endpoints clearly marked as not implemented", async () => {
    vi.mocked(api.checkPermission).mockRejectedValueOnce(new api.ApiError(404, "Not Found"));
    render(<RoleFeaturePage title="Users" description="Manage accounts" endpoint="/rbac/admin/users" />);
    expect((await screen.findAllByText("This feature is not implemented yet.")).length).toBeGreaterThan(0);
    expect(screen.getByText("Not implemented")).toBeInTheDocument();
    expect(screen.queryByText("Module ready")).not.toBeInTheDocument();
  });
});
