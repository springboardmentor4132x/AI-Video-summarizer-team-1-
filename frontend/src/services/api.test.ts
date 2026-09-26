import { afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL } from "../config";
import { ApiError, downloadSummary, generateSummary, getCurrentUser, getSummary, getTranscript, getVideoMediaBlobUrl, getVideos, login, register } from "./api";

describe("API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses the configured local backend URL", () => {
    expect(API_BASE_URL).toBe("http://127.0.0.1:8000");
  });

  it("preserves useful messages for ordinary HTTP errors", async () => {
    for (const status of [401, 403, 404, 422, 500]) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: `backend error ${status}` }), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      ));

      const expectedMessage = status === 401 ? "Invalid email or password." : status === 403
        ? "Your account does not have permission to access this workspace."
        : `backend error ${status}`;
      await expect(login("user@example.com", "password")).rejects.toMatchObject({
        status,
        message: expectedMessage,
      });
    }
  });

  it("uses the connection message only when fetch cannot produce a response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(login("user@example.com", "password")).rejects.toEqual(
      new ApiError(
        0,
        "Cannot connect to the ClipMind AI backend. Check that the frontend is opened from the configured local address and that the backend is reachable.",
      ),
    );
  });

  it("maps the registration form's full_name to the backend's required name field", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 7, name: "Test User", email: "user@example.com", role: "Content Creator" }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await register({
      full_name: " Test User ",
      email: " user@example.com ",
      password: "test-password",
      confirm_password: "test-password",
      role: "Content Creator",
    });

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API_BASE_URL}/auth/register`);
    expect(options.method).toBe("POST");
    expect(JSON.parse(String(options.body))).toEqual({
      name: "Test User",
      email: "user@example.com",
      password: "test-password",
      role: "Content Creator",
    });
  });

  it("normalizes the backend name field for authenticated frontend user state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      id: 7,
      name: "Test User",
      email: "user@example.com",
      role: "Content Creator",
      created_at: "2026-09-26T00:00:00Z",
    }), { status: 200, headers: { "Content-Type": "application/json" } })));

    await expect(getCurrentUser("valid-test-token")).resolves.toMatchObject({
      name: "Test User",
      full_name: "Test User",
      role: "Content Creator",
    });
  });

  it("loads video media from the owner-scoped API route with the bearer token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(["video"]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:video") });

    await expect(getVideoMediaBlobUrl("valid-test-token", "42")).resolves.toBe("blob:video");
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE_URL}/videos/42/media`, {
      headers: { Authorization: "Bearer valid-test-token" },
    });
  });

  it("normalizes Whisper start/end timestamps for transcript playback", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      id: 3, video_id: 42, text: "Hello", status: "COMPLETED", language: "en",
      segments: [{ start: 12, end: 15, text: "Hello" }],
      created_at: "2026-09-26T00:00:00Z", updated_at: null,
    }), { status: 200, headers: { "Content-Type": "application/json" } })));

    await expect(getTranscript("valid-test-token", 42)).resolves.toMatchObject({
      segments: [{ start_time: 12, end_time: 15, text: "Hello" }],
    });
  });

  it("maps the real backend summary fields and uses the supported regenerate route", async () => {
    const summaryResponse = () => new Response(JSON.stringify({
      id: 8, transcript_id: 3, short_summary: "Short", detailed_summary: "Detailed",
      status: "COMPLETED", created_at: "2026-09-26T00:00:00Z", updated_at: null,
    }), { status: 200, headers: { "Content-Type": "application/json" } });
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(summaryResponse()));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getSummary("valid-test-token", 42)).resolves.toMatchObject({
      video_id: "42", overview: "Short", content: "Detailed", detailed_summary: "Detailed",
    });
    await generateSummary("valid-test-token", 42, true);
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`${API_BASE_URL}/videos/42/summary/regenerate`);
  });

  it("downloads a summary through the authenticated owner-scoped route", async () => {
    const blob = new Blob(["Short Summary\nA true summary."], { type: "text/plain" });
    const fetchMock = vi.fn().mockResolvedValue(new Response(blob, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(downloadSummary("valid-test-token", 42)).resolves.toBeInstanceOf(Blob);
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE_URL}/videos/42/summary/download`, {
      headers: { Authorization: "Bearer valid-test-token" },
    });
  });

  it("maps the owner-scoped backend video status for library and quiz filtering", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([{
      id: 42, user_id: 7, filename: "lesson.mp4", status: "completed", uploaded_at: "2026-09-26T00:00:00Z",
    }]), { status: 200, headers: { "Content-Type": "application/json" } })));

    await expect(getVideos("valid-test-token")).resolves.toMatchObject([{
      id: "42", owner_id: "7", filename: "lesson.mp4", processing_status: "COMPLETED", source_type: "UPLOAD",
    }]);
  });
});
