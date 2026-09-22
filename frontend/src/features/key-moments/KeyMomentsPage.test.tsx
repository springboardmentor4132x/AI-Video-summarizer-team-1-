// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KeyMomentsPage } from "./KeyMomentsPage";

const { getKeyMoments, generateKeyMoments } = vi.hoisted(() => ({
  getKeyMoments: vi.fn(),
  generateKeyMoments: vi.fn(),
}));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ token: "token", user: { id: 7, role: "Content Creator" } }),
}));

vi.mock("../../services/api", () => ({
  getKeyMoments,
  generateKeyMoments,
  getVideoMediaUrl: () => "/media/video.mp4",
}));

const sampleVideo = {
  id: 1,
  filename: "lesson.mp4",
  status: "completed",
  uploaded_at: "2026-09-21T00:00:00Z",
};

const sampleMoment = {
  id: 2,
  start_time: 300,
  end_time: 360,
  title: "Machine learning definition",
  topic: "Machine Learning",
  text: "Machine learning uses data.",
  importance_score: 0.86,
  highlight_path: null,
};

afterEach(() => {
  cleanup();
});

describe("KeyMomentsPage", () => {
  beforeEach(() => {
    getKeyMoments.mockResolvedValue({
      video_id: 1,
      status: "completed",
      key_moments: [sampleMoment],
    });
  });

  it("renders topics and seeks the player when a timestamp is clicked", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={[{ pathname: "/creator/key-moments/1", state: { video: sampleVideo } }]}>
        <Routes><Route path="/creator/key-moments/:videoId" element={<KeyMomentsPage />} /></Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(container.querySelector(".key-moments")).toBeTruthy());
    expect(screen.getAllByText("Machine Learning").length).toBeGreaterThan(0);

    const player = container.querySelector("video") as HTMLVideoElement;
    fireEvent.click(screen.getByRole("button", { name: /05:00 · Machine learning definition/ }));
    expect(player.currentTime).toBe(300);
  });

  it("renders correctly when accessed via the Learner route", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={[{ pathname: "/learner/key-moments/1", state: { video: sampleVideo } }]}>
        <Routes><Route path="/learner/key-moments/:videoId" element={<KeyMomentsPage />} /></Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(container.querySelector(".key-moments")).toBeTruthy());
    expect(screen.getAllByText("Machine Learning").length).toBeGreaterThan(0);
    expect(container.textContent).toContain("Machine learning definition");
  });

  it("renders correctly when accessed via the Educator route", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={[{ pathname: "/educator/key-moments/1", state: { video: sampleVideo } }]}>
        <Routes><Route path="/educator/key-moments/:videoId" element={<KeyMomentsPage />} /></Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(container.querySelector(".key-moments")).toBeTruthy());
    expect(screen.getAllByText("Machine Learning").length).toBeGreaterThan(0);
    expect(container.textContent).toContain("Machine learning definition");
  });

  it("shows a back-link prompt when state.video is missing", () => {
    render(
      <MemoryRouter initialEntries={[{ pathname: "/creator/key-moments/1" }]}>
        <Routes><Route path="/creator/key-moments/:videoId" element={<KeyMomentsPage />} /></Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Choose a video from the library")).toBeTruthy();
  });
});
