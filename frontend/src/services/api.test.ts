import { afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL } from "../config";
import { ApiError, login } from "./api";

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
});