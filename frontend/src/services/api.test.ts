import { afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL } from "../config";
import { ApiError, getCurrentUser, login, register } from "./api";

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
});
