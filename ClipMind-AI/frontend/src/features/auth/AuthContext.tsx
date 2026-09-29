import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getCurrentUser, login as loginRequest } from "../../services/api";
import type { CurrentUser } from "../../types/auth";

interface AuthContextValue {
  user: CurrentUser | null;
  token: string | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);
const TOKEN_KEY = "clipmind_access_token";

function readStoredToken() {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(TOKEN_KEY)?.trim();
  if (!value || ["undefined", "null", ""].includes(value.toLowerCase())) {
    window.localStorage.removeItem(TOKEN_KEY);
    return null;
  }
  return value;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => readStoredToken());
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(Boolean(token));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      setUser(null);
      return;
    }
    getCurrentUser(token)
      .then(setUser)
      .catch(reason => {
        const message = reason instanceof Error ? reason.message : "Authentication failed";
        if (/session has expired|Could not validate credentials|unauthorized|forbidden|permission/i.test(message)) {
          window.localStorage.removeItem(TOKEN_KEY);
          setToken(null);
          setUser(null);
          setError("Your session has expired. Please log in again.");
          return;
        }
        if (/Cannot connect to the ClipMind AI backend|temporarily unavailable|server error/i.test(message)) {
          setError(message);
        }
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, [token]);

  async function login(email: string, password: string) {
    setError(null);
    try {
      const response = await loginRequest(email, password);
      const nextToken = response.access_token?.trim();
      if (!nextToken || ["undefined", "null", ""].includes(nextToken.toLowerCase())) {
        throw new Error("Your session has expired. Please log in again.");
      }
      window.localStorage.setItem(TOKEN_KEY, nextToken);
      setToken(nextToken);
      setUser(await getCurrentUser(nextToken));
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Authentication failed";
      if (/Cannot connect to the ClipMind AI backend/i.test(message)) {
        setError("Cannot connect to the ClipMind AI backend.");
      } else if (/Invalid email or password/i.test(message)) {
        setError("Invalid email or password.");
      } else if (/permission to access this workspace|forbidden/i.test(message)) {
        setError("Your account does not have permission to access this workspace.");
      } else if (/Server error|temporarily unavailable/i.test(message)) {
        setError("Authentication service is temporarily unavailable.");
      } else {
        setError(message || "Authentication failed");
      }
      window.localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setUser(null);
      throw reason;
    }
  }

  function logout() {
    window.localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
    setError(null);
  }

  return <AuthContext.Provider value={{ user, token, loading, error, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
