import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { AnalyticsPage, MCQQuizPage, TranscriptModalContent, VideoUploadPage } from "./pages";
import { Modal } from "./components/Modal";
import { SummaryPanel } from "./features/summaries/SummaryPanel";
import { useAuth } from "./features/auth/AuthContext";

vi.mock("./features/auth/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("./services/api", () => ({
  uploadVideo: vi.fn(),
  processYouTubeVideo: vi.fn(),
  getAdminAnalytics: vi.fn(),
  getCreatorAnalytics: vi.fn(),
  postAdminAnalyticsAIInsights: vi.fn(),
  postCreatorAnalyticsAIInsights: vi.fn(),
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

describe("Frontend pages", () => {
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

  it("shows the full transcript text without segment timestamps in a scroll-locked modal", async () => {
    const transcriptText = "Opening sentence.\nClosing sentence.";
    const onClose = vi.fn();
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const createObjectURL = vi.fn((_blob: Blob) => "blob:transcript-test");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    const clickedAnchors: HTMLAnchorElement[] = [];
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clickedAnchors.push(this);
    });
    const view = render(
      <Modal open title="Video Transcript" onClose={onClose}>
        <TranscriptModalContent
          data={{
            transcript: {
              text: transcriptText,
              segments: [
                { start_time: 0, end_time: 15, text: "Opening sentence." },
                { start_time: 15, end_time: 92, text: "Closing sentence." },
              ],
              status: "COMPLETED",
            },
            loading: false,
            error: null,
          } as any}
          videoName="Lesson/Part?.mp4"
          onRetry={vi.fn()}
          onClose={onClose}
        />
      </Modal>,
    );

    expect(screen.getByLabelText("Full transcript").textContent).toBe(transcriptText);
    expect(screen.queryByText("00:00")).not.toBeInTheDocument();
    expect(screen.queryByText("00:15")).not.toBeInTheDocument();
    expect(screen.queryByText("01:32")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close dialog" })).toBeInTheDocument();
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.click(screen.getByRole("button", { name: "Download Transcript" }));
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(await (createObjectURL.mock.calls[0][0] as Blob).text()).toBe(transcriptText);
    expect(clickedAnchors).toHaveLength(1);
    expect(clickedAnchors[0].download).toBe("Lesson-Part-transcript.txt");
    expect(clickedAnchors[0].href).toBe("blob:transcript-test");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:transcript-test");
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();

    view.unmount();
    anchorClick.mockRestore();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: originalCreateObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: originalRevokeObjectURL });
  });

  it("renders the Gemini summary fields in the existing AI Summary panel", async () => {
    mockedUseAuth.mockReturnValue({
      token: "token-123",
      user: null,
      loading: false,
      error: null,
      login: vi.fn(),
      logout: vi.fn(),
    } as any);
    vi.mocked(api.getSummary).mockResolvedValue({
      id: "summary-1",
      video_id: "video-1",
      content: "The long summary expands on the transcript's key ideas.",
      overview: "The short summary captures the main subject.",
      main_points: ["The transcript explains the core process."],
      key_takeaways: ["Review the process before applying it."],
      duration_seconds: 120,
      status: "COMPLETED",
      error_message: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    render(<SummaryPanel videoId="video-1" videoName="Lesson.mp4" durationSeconds={120} />);
    fireEvent.click(screen.getByRole("button", { name: "AI Summary" }));

    expect(await screen.findByText("The short summary captures the main subject.")).toBeInTheDocument();
    expect(screen.getByText("Short Summary")).toBeInTheDocument();
    expect(screen.getByText("Long Summary")).toBeInTheDocument();
    expect(screen.getByText("The long summary expands on the transcript's key ideas.")).toBeInTheDocument();
    expect(screen.getByText("Key Points")).toBeInTheDocument();
    expect(screen.getByText("The transcript explains the core process.")).toBeInTheDocument();
    expect(screen.getByText("Duration")).toBeInTheDocument();
  });

  it("downloads stored summary notes as sanitized plain text without another generation request", async () => {
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const createObjectURL = vi.fn((_blob: Blob) => "blob:summary-notes");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    const clickedAnchors: HTMLAnchorElement[] = [];
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clickedAnchors.push(this);
    });
    vi.mocked(api.getSummary).mockReset();
    vi.mocked(api.generateSummary).mockReset();
    vi.mocked(api.getSummary).mockResolvedValue({
      id: "summary-db-id",
      video_id: "video-db-id",
      content: "The detailed notes explain the process and its conclusion.",
      overview: "The short summary describes the lesson.",
      main_points: ["The process has distinct phases.", "Review improves the result."],
      key_takeaways: ["Review improves the result.", "Apply the process to the selected case."],
      duration_seconds: 180,
      status: "COMPLETED",
      error_message: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    const view = render(<SummaryPanel videoId="video-db-id" videoName="Study: Unit?.mp4" durationSeconds={180} />);
    fireEvent.click(screen.getByRole("button", { name: "AI Summary" }));
    expect(await screen.findByText("The short summary describes the lesson.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download Summary" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Download Summary" }));

    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    const downloadedText = await (createObjectURL.mock.calls[0][0] as Blob).text();
    expect(downloadedText).toContain("Short Summary\nThe short summary describes the lesson.");
    expect(downloadedText).toContain("Detailed Notes / Long Summary\nThe detailed notes explain the process and its conclusion.");
    expect(downloadedText).toContain("Key Points\n- The process has distinct phases.\n- Review improves the result.");
    expect(downloadedText).toContain("Key Takeaways\n- Apply the process to the selected case.");
    expect(downloadedText).not.toMatch(/\b\d{2}:\d{2}\b/);
    expect(downloadedText).not.toContain("summary-db-id");
    expect(downloadedText).not.toContain("video-db-id");
    expect(clickedAnchors).toHaveLength(1);
    expect(clickedAnchors[0].download).toBe("Study- Unit-AI-Notes.txt");
    expect(clickedAnchors[0].href).toBe("blob:summary-notes");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:summary-notes");
    expect(api.getSummary).toHaveBeenCalledTimes(1);
    expect(api.generateSummary).not.toHaveBeenCalled();

    view.unmount();
    anchorClick.mockRestore();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: originalCreateObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: originalRevokeObjectURL });
  });

  it("does not offer a summary download when no stored summary is available", async () => {
    vi.mocked(api.getSummary).mockReset();
    vi.mocked(api.generateSummary).mockReset();
    vi.mocked(api.getSummary).mockRejectedValue(new Error("Summary does not exist"));

    render(<SummaryPanel videoId="video-1" videoName="Lesson.mp4" durationSeconds={null} />);
    fireEvent.click(screen.getByRole("button", { name: "AI Summary" }));

    expect(await screen.findByText("AI Summary is not available for this video yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download Summary" })).not.toBeInTheDocument();
    expect(api.generateSummary).not.toHaveBeenCalled();
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

  it("shows the real upload source breakdown with file and YouTube counts", async () => {
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

    const dashboard = {
      overview: {
        total_videos: 16,
        completed_videos: 12,
        processing_videos: 2,
        failed_videos: 1,
        uploaded_videos: 10,
        uploaded_video_count: 12,
        youtube_video_count: 4,
        total_duration_seconds: 3600,
        average_duration_seconds: 225,
        total_summaries: 9,
        total_transcripts: 15,
        total_key_moments: 20,
        total_users: 1,
      },
      video_analytics: {
        upload_activity: [],
        processing_activity: [],
        status_distribution: [],
        recent_videos: [],
      },
      summary_reports: {
        total_summaries: 9,
        completed_summaries: 9,
        videos_with_summaries: 9,
        generation_rate_percentage: 90,
        total_summary_characters: 100,
        recent_activity: [],
        total_summary_words: 200,
        average_summary_words: 22.2,
        longest_summary_words: 50,
        shortest_summary_words: 10,
      },
      content_insights: {
        total_transcripts: 15,
        total_transcript_characters: 200,
        average_transcript_characters: 13.3,
        total_summary_characters: 100,
        top_keywords: [],
        total_transcript_words: 300,
        average_words_per_video: 18.75,
        key_moment_density: 0.0667,
      },
      key_moment_analytics: {
        total_key_moments: 20,
        videos_with_key_moments: 6,
        average_per_video: 1.25,
        total_duration_seconds: 120,
        average_duration_seconds: 6,
        recent_activity: [],
        average_importance: 0.72,
        highest_importance: 0.95,
        by_video: [],
      },
      usage: {
        total_users: 1,
        users_by_role: [],
        upload_activity: [],
        processing_activity: [],
      },
      processing_insights: {
        videos: { count: 16, coverage_percentage: 100 },
        transcripts: { count: 15, coverage_percentage: 94 },
        summaries: { count: 9, coverage_percentage: 60 },
        key_moments: { count: 20, coverage_percentage: 100 },
      },
      transcript_insights: {
        total_transcripts: 15,
        total_words: 300,
        average_words_per_transcript: 20,
        longest_transcript_words: 150,
        shortest_transcript_words: 5,
        total_characters: 200,
        average_characters: 13.3,
      },
      keyword_insights: [],
      content_insights_v2: {
        total_transcripts: 15,
        total_transcript_characters: 200,
        average_transcript_characters: 13.3,
        total_summary_characters: 100,
        top_keywords: [],
        total_transcript_words: 300,
        average_words_per_video: 18.75,
        key_moment_density: 0.0667,
      },
      summary_insights: {
        total_summaries: 9,
        completed_summaries: 9,
        videos_with_summaries: 9,
        generation_rate_percentage: 90,
        total_summary_characters: 100,
        recent_activity: [],
        total_summary_words: 200,
        average_summary_words: 22.2,
        longest_summary_words: 50,
        shortest_summary_words: 10,
      },
      key_moment_insights: {
        total_key_moments: 20,
        videos_with_key_moments: 6,
        average_per_video: 1.25,
        total_duration_seconds: 120,
        average_duration_seconds: 6,
        recent_activity: [],
        average_importance: 0.72,
        highest_importance: 0.95,
        by_video: [
          { video_id: "video-uuid-1", label: "video-1062668a2c_std.mp4", count: 2 },
          { video_id: "video-uuid-2", label: "video-1062668a2c_std.mp4", count: 1 },
        ],
      },
      recent_activity: [],
      recent_videos: [
        { id: "video-uuid-1", filename: "video-1062668a2c_std.mp4", ai_score: 80 },
        { id: "video-uuid-2", filename: "video-1062668a2c_std.mp4", ai_score: 70 },
      ],
      intelligence_score: {
        score: 88,
        explanation: "Strong coverage across 16 videos.",
        components: [],
      },
      ai_insights: [],
      top_topics: [{ topic: "python", percentage: 70, frequency: 14, video_count: 3, related_keywords: ["python"], key_moment_count: 2, summary_count: 1 }],
      keyword_intelligence: [{ keyword: "python", frequency: 14, share_percentage: 70, video_count: 3 }],
      content_activity: [],
      compression_insights: {
        average_transcript_words: 20,
        average_summary_words: 22.2,
        compression_ratio: 1.11,
      },
      importance_distribution: [],
    } as any;
    vi.mocked(api.getCreatorAnalytics).mockResolvedValue(dashboard);
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    let resolveAiInsights: ((result: any) => void) | null = null;
    vi.mocked(api.postCreatorAnalyticsAIInsights)
      .mockImplementationOnce(() => new Promise(resolve => { resolveAiInsights = resolve; }))
      .mockRejectedValueOnce(new Error("AI insights are temporarily unavailable. Your analytics data is still available."));

    render(<AnalyticsPage />);

    await waitFor(() => expect(vi.mocked(api.getCreatorAnalytics)).toHaveBeenCalledWith("token-123", {}));
    expect(screen.getByRole("status")).toHaveTextContent("Generating AI Insights...");
    await act(async () => {
      resolveAiInsights?.({
        analytics: dashboard,
        ai_insights: {
          overview: "Your verified analytics show a 16-video library with source and processing variation.",
          key_insight: "File uploads are the more frequent source in this period.",
          attention: [{ title: "Review failed processing", description: "One video is recorded as failed.", severity: "medium" }],
          content_insight: "Python is the most frequent supplied topic.",
          usage_insight: "Upload and processing activity are available for this period.",
          summary_insight: "Nine summaries are recorded with 90% coverage.",
          keyword_insight: "Python appears 14 times across three videos.",
          recommendations: ["Review the failed video."],
        },
      });
    });
    expect(await screen.findByText("Your verified analytics show a 16-video library with source and processing variation.")).toBeInTheDocument();
    expect(screen.getByText("File Uploads")).toBeInTheDocument();
    expect(screen.getByText("YouTube URL Uploads")).toBeInTheDocument();
    expect(screen.getByText("VIDEO ANALYTICS")).toBeInTheDocument();
    expect(screen.getByText("SUMMARY REPORTS")).toBeInTheDocument();
    expect(screen.getByText("CONTENT INSIGHTS")).toBeInTheDocument();
    expect(screen.getByText("USAGE STATISTICS")).toBeInTheDocument();
    expect(screen.getByText("KEYWORD INTELLIGENCE")).toBeInTheDocument();
    expect(screen.getAllByText("python").length).toBeGreaterThan(0);
    expect(screen.getByText("Python appears 14 times across three videos.")).toBeInTheDocument();
    expect(await screen.findByText(/Upload Source Breakdown/i)).toBeInTheDocument();
    expect(screen.getAllByText("12").length).toBeGreaterThan(0);
    expect(screen.getAllByText("4").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /Refresh AI Insights/i }));
    expect(screen.getByRole("status")).toHaveTextContent("Generating AI Insights...");
    expect(await screen.findByRole("alert")).toHaveTextContent("AI insights are temporarily unavailable.");
    expect(screen.getByText("Total Videos")).toBeInTheDocument();
    expect(screen.getByText("YouTube URL Uploads")).toBeInTheDocument();
    expect(vi.mocked(api.postCreatorAnalyticsAIInsights)).toHaveBeenCalledTimes(2);
    expect(consoleError.mock.calls.flat().join(" ")).not.toContain("Encountered two children with the same key");
    consoleError.mockRestore();
  });
});
