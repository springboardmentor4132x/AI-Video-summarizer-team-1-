// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockGetCurrentUser = vi.fn();

vi.mock("../../services/api", () => ({
  AUTH_EXPIRED_EVENT: "clipmind:auth-expired",
  getCurrentUser: (...args: unknown[]) => mockGetCurrentUser(...args),
  login: vi.fn(),
}));

import { AuthProvider, useAuth } from "./AuthContext";

function AuthProbe() {
  const { user, error } = useAuth();
  return (
    <>
      <span>{user?.name ?? "Signed out"}</span>
      {error && <span role="alert">{error}</span>}
      <button onClick={() => window.dispatchEvent(new Event("clipmind:auth-expired"))}>Expire session</button>
    </>
  );
}

afterEach(cleanup);

beforeEach(() => {
  localStorage.clear();
  mockGetCurrentUser.mockReset();
});

describe("AuthContext session handling", () => {
  it("clears an expired token and signs the user out after an API 401", async () => {
    localStorage.setItem("clipmind_access_token", "expired-token");
    mockGetCurrentUser.mockResolvedValue({
      id: 1,
      name: "Validation Creator",
      email: "creator@example.com",
      role: "Content Creator",
      created_at: "2026-09-24T00:00:00Z",
    });

    render(<AuthProvider><AuthProbe /></AuthProvider>);
    expect(await screen.findByText("Validation Creator")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Expire session" }));

    await waitFor(() => expect(screen.getByText("Signed out")).toBeTruthy());
    expect(localStorage.getItem("clipmind_access_token")).toBeNull();
    expect(screen.getByRole("alert").textContent).toBe("Your session has expired. Please sign in again.");
  });
});
