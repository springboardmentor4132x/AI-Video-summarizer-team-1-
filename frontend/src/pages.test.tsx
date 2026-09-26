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
  register: vi.fn(),
  checkPermission: vi.fn(),
  getVideoMediaUrl: vi.fn(),
}));

const mockedUseAuth = vi.mocked(useAuth);
const api = await import("./services/api");
const mockedUploadVideo = vi.mocked(api.uploadVideo);
const mockedProcessYouTubeVideo = vi.mocked(api.processYouTubeVideo);

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
    mockedProcessYouTubeVideo.mockReset();
  });

  it("defaults to the upload tab and keeps the existing upload workflow available", () => {
    render(<VideoUploadPage />);
    expect(screen.getByRole("button", { name: "Upload Video" })).toHaveClass("primary-button");
    expect(screen.getByLabelText(/choose a video file|Drop your video here/i)).toBeInTheDocument();
  });

  it("switches to the YouTube URL tab and validates empty and invalid URLs", async () => {
    render(<VideoUploadPage />);
    fireEvent.click(screen.getByRole("button", { name: "YouTube URL" }));

    const input = screen.getByPlaceholderText("Paste YouTube video URL");
    fireEvent.click(screen.getByRole("button", { name: "Process Video" }));
    expect(await screen.findByText("Please paste a YouTube video URL.")).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "https://example.com/not-youtube" } });
    fireEvent.click(screen.getByRole("button", { name: "Process Video" }));
    expect(await screen.findByText("Please enter a valid YouTube URL.")).toBeInTheDocument();
  });

  it("submits a valid YouTube URL and shows the success state", async () => {
    mockedProcessYouTubeVideo.mockResolvedValue({
      video_id: "abc",
      source_type: "YOUTUBE",
      source_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      status: "PROCESSING",
    });

    render(<VideoUploadPage />);
    fireEvent.click(screen.getByRole("button", { name: "YouTube URL" }));
    fireEvent.change(screen.getByPlaceholderText("Paste YouTube video URL"), {
      target: { value: "https://www.youtube.com/watch?v=dQw4w9WgXcQ" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Process Video" }));

    await waitFor(() => expect(mockedProcessYouTubeVideo).toHaveBeenCalledWith("token-123", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"));
    expect(await screen.findByText("YouTube video accepted", { exact: true })).toBeInTheDocument();
    expect(await screen.findByText(/Processing status: PROCESSING/i)).toBeInTheDocument();
  });

  it("renders the dedicated MCQ quiz flow with real answer options", async () => {
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
    vi.mocked(api.getExpectedMcqs).mockResolvedValue([
      {
        question: "What type of programming language is Python?",
        options: [
          "Low-level programming language",
          "High-level general-purpose programming language",
          "Assembly language",
          "Machine language",
        ],
        correct_answer: "High-level general-purpose programming language",
        explanation: "The transcript describes Python as a high-level general-purpose language.",
        difficulty: "Easy",
        topic: "Python Basics",
        source: "Transcript",
        timestamp: "00:00",
      },
    ]);

    render(<MCQQuizPage />);

    await waitFor(() => expect(api.getVideos).toHaveBeenCalledWith("token-123", 500));
    fireEvent.change(screen.getByLabelText(/Select Video/i), { target: { value: "video-1" } });
    fireEvent.change(screen.getByLabelText(/Number of Questions/i), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: /Generate Quiz/i }));

    expect(await screen.findByText("Question 1 of 1")).toBeInTheDocument();
    expect(await screen.findByText("What type of programming language is Python?")).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(4);

    fireEvent.click(screen.getByLabelText("B. High-level general-purpose programming language"));
    fireEvent.click(screen.getByRole("button", { name: /Submit Answer/i }));
    expect(await screen.findByText("✅ Correct!")).toBeInTheDocument();
    expect(await screen.findByText(/Correct Answer:/i)).toBeInTheDocument();
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
