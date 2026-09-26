// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockGetCreatorAnalytics = vi.fn();
const mockGetAdminAnalytics = vi.fn();

vi.mock("./features/auth/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      name: "Creator Test",
      email: "creator@example.com",
      role: "Content Creator" as const,
      created_at: "2026-09-23T00:00:00Z",
    },
    token: "fake-jwt-token",
    loading: false,
    error: null,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock("./services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./services/api")>();
  return {
    ...actual,
    getCreatorAnalytics: (...args: unknown[]) => mockGetCreatorAnalytics(...args),
    getAdminAnalytics: (...args: unknown[]) => mockGetAdminAnalytics(...args),
  };
});

import { AnalyticsPage } from "./pages";
import type * as api from "./services/api";

afterEach(() => {
  cleanup();
});

const mockAnalyticsDashboard: api.AnalyticsDashboard = {
  overview: {
    total_videos: 5,
    completed_videos: 4,
    processing_videos: 1,
    failed_videos: 0,
    uploaded_videos: 0,
    total_duration_seconds: 450,
    average_duration_seconds: 90,
    total_summaries: 3,
    total_transcripts: 4,
    total_key_moments: 12,
    total_users: 1,
  },
  video_analytics: {
    upload_activity: [{ date: "2026-09-23", count: 5 }],
    processing_activity: [{ date: "2026-09-23", count: 4 }],
    status_distribution: [{ label: "completed", count: 4 }, { label: "processing", count: 1 }],
    recent_videos: [
      {
        id: "1",
        filename: "test_demo.mp4",
        owner_name: "Creator Test",
        status: "completed",
        uploaded_at: "2026-09-23T10:00:00Z",
        duration_seconds: 120,
        transcript_status: "COMPLETED",
        summary_status: "COMPLETED",
        key_moment_count: 3,
        transcript_word_count: 500,
        transcript_character_count: 2800,
        summary_word_count: 85,
        topic_count: 4,
        top_topics: ["neural networks", "transformers"],
        top_keywords: ["neural", "networks"],
        ai_score: 88,
        ai_score_components: { "Processing": 100, "Transcript": 100 },
        average_importance: 0.85,
        highest_importance: 0.95,
        main_points_count: 0,
        key_takeaways_count: 0,
      }
    ],
  },
  summary_reports: {
    total_summaries: 3,
    completed_summaries: 3,
    videos_with_summaries: 3,
    generation_rate_percentage: 75,
    total_summary_characters: 1200,
    recent_activity: [],
    total_summary_words: 250,
    average_summary_words: 83.3,
    longest_summary_words: 100,
    shortest_summary_words: 60,
  },
  content_insights: {
    total_transcripts: 4,
    total_transcript_characters: 10000,
    average_transcript_characters: 2500,
    total_summary_characters: 1200,
    top_keywords: [{ keyword: "neural", count: 15, frequency: 15, rank: 1 }],
    total_transcript_words: 2000,
    average_words_per_video: 400,
    key_moment_density: 0.006,
  },
  key_moment_analytics: {
    total_key_moments: 12,
    videos_with_key_moments: 3,
    average_per_video: 2.4,
    total_duration_seconds: 180,
    average_duration_seconds: 15,
    recent_activity: [],
    average_importance: 0.82,
    highest_importance: 0.95,
    by_video: [{ label: "test_demo.mp4", count: 3 }],
  },
  usage: {
    total_users: 1,
    users_by_role: [{ label: "Content Creator", count: 1 }],
    upload_activity: [],
    processing_activity: [],
  },
  processing_insights: {
    videos: { count: 5, coverage_percentage: 100 },
    transcripts: { count: 4, coverage_percentage: 80 },
    summaries: { count: 3, coverage_percentage: 75 },
    key_moments: { count: 3, coverage_percentage: 75 },
  },
  transcript_insights: {
    total_transcripts: 4,
    total_words: 2000,
    average_words_per_transcript: 500,
    longest_transcript_words: 600,
    shortest_transcript_words: 400,
    total_characters: 10000,
    average_characters: 2500,
  },
  keyword_insights: [{ keyword: "neural", count: 15, frequency: 15, rank: 1 }],
  content_insights_v2: {
    total_transcripts: 4,
    total_transcript_characters: 10000,
    average_transcript_characters: 2500,
    total_summary_characters: 1200,
    top_keywords: [{ keyword: "neural", count: 15, frequency: 15, rank: 1 }],
    total_transcript_words: 2000,
    average_words_per_video: 400,
    key_moment_density: 0.006,
  },
  summary_insights: {
    total_summaries: 3,
    completed_summaries: 3,
    videos_with_summaries: 3,
    generation_rate_percentage: 75,
    total_summary_characters: 1200,
    recent_activity: [],
    total_summary_words: 250,
    average_summary_words: 83.3,
    longest_summary_words: 100,
    shortest_summary_words: 60,
  },
  key_moment_insights: {
    total_key_moments: 12,
    videos_with_key_moments: 3,
    average_per_video: 2.4,
    total_duration_seconds: 180,
    average_duration_seconds: 15,
    recent_activity: [],
    average_importance: 0.82,
    highest_importance: 0.95,
    by_video: [{ label: "test_demo.mp4", count: 3 }],
  },
  recent_activity: [],
  recent_videos: [
    {
      id: "1",
      filename: "test_demo.mp4",
      owner_name: "Creator Test",
      status: "completed",
      uploaded_at: "2026-09-23T10:00:00Z",
      duration_seconds: 120,
      transcript_status: "COMPLETED",
      summary_status: "COMPLETED",
      key_moment_count: 3,
      transcript_word_count: 500,
      transcript_character_count: 2800,
      summary_word_count: 85,
      topic_count: 4,
      top_topics: ["neural networks", "transformers"],
      top_keywords: ["neural", "networks"],
      ai_score: 88,
      ai_score_components: { "Processing": 100, "Transcript": 100 },
      average_importance: 0.85,
      highest_importance: 0.95,
      main_points_count: 0,
      key_takeaways_count: 0,
    }
  ],
  intelligence_score: {
    score: 88,
    explanation: "Strong coverage across 5 videos: 4 transcripts, 3 summaries, and 12 detected key moments.",
    components: [{ label: "Processing", score: 100, weight: 0.25 }],
  },
  ai_insights: [
    { category: "TOPIC", title: "Leading content topic", message: "Neural networks is the most frequently discussed topic.", metric: "45% of keywords" }
  ],
  top_topics: [
    { topic: "neural networks", percentage: 45, frequency: 15, video_count: 3, related_keywords: ["neural"], key_moment_count: 3, summary_count: 2 }
  ],
  keyword_intelligence: [
    { keyword: "neural", frequency: 15, share_percentage: 45, video_count: 3 }
  ],
  content_activity: [
    { date: "2026-09-23", transcripts: 4, summaries: 3, key_moments: 12 }
  ],
  compression_insights: {
    average_transcript_words: 500,
    average_summary_words: 85,
    compression_ratio: 0.17,
  },
  importance_distribution: [
    { label: "High (0.67-1.00)", count: 12, average_importance: 0.82 }
  ],
};

describe("AnalyticsPage", () => {
  beforeEach(() => {
    mockGetCreatorAnalytics.mockReset();
    mockGetAdminAnalytics.mockReset();
  });

  it("renders metric cards and content intelligence when API returns data", async () => {
    mockGetCreatorAnalytics.mockResolvedValue(mockAnalyticsDashboard);

    render(
      <MemoryRouter>
        <AnalyticsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("AI content intelligence at a glance")).toBeTruthy();
    });

    expect(screen.getByText("Videos analyzed")).toBeTruthy();
    expect(screen.getAllByText("5").length).toBeGreaterThan(0);
    expect(screen.getByText("Transcripts", { selector: ".analytics-metric-label" })).toBeTruthy();
    expect(screen.getAllByText("4").length).toBeGreaterThan(0);
    expect(screen.getByText("AI summaries", { selector: ".analytics-metric-label" })).toBeTruthy();
    expect(screen.getByText("Key moments", { selector: ".analytics-metric-label" })).toBeTruthy();
    expect(screen.getAllByText("12").length).toBeGreaterThan(0);
    expect(screen.getByText("test_demo.mp4", { selector: ".video-intelligence-table strong" })).toBeTruthy();
  });

  it("counts completed summaries in the AI summaries metric", async () => {
    mockGetCreatorAnalytics.mockResolvedValue({
      ...mockAnalyticsDashboard,
      overview: { ...mockAnalyticsDashboard.overview, total_summaries: 5 },
      summary_insights: { ...mockAnalyticsDashboard.summary_insights, completed_summaries: 3 },
    });

    render(<MemoryRouter><AnalyticsPage /></MemoryRouter>);

    await waitFor(() => expect(screen.getByText("AI summaries", { selector: ".analytics-metric-label" })).toBeTruthy());
    const metric = screen.getByText("AI summaries", { selector: ".analytics-metric-label" }).closest(".analytics-metric");
    expect(metric?.querySelector("strong")?.textContent).toBe("3");
  });

  it("handles API failure gracefully with clear error and retry button without fake zero metrics", async () => {
    mockGetCreatorAnalytics.mockRejectedValue(new Error("Network timeout"));

    render(
      <MemoryRouter>
        <AnalyticsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Unable to load analytics")).toBeTruthy();
    });

    expect(screen.getByText("Network timeout")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Try again/i })).toBeTruthy();
    expect(screen.queryByText("AI content intelligence at a glance")).toBeNull();
  });

  it("opens video detail modal when a video row is clicked", async () => {
    mockGetCreatorAnalytics.mockResolvedValue(mockAnalyticsDashboard);
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <AnalyticsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("test_demo.mp4", { selector: ".video-intelligence-table strong" })).toBeTruthy();
    });

    await user.click(screen.getByText("test_demo.mp4", { selector: ".video-intelligence-table strong" }).closest("tr")!);

    expect(screen.getByRole("dialog", { name: /test_demo\.mp4 intelligence details/i })).toBeTruthy();
    expect(screen.getByText("Video overview")).toBeTruthy();
  });
});
