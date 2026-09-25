import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { AUTH_EXPIRED_EVENT, getCurrentUser, login as loginRequest } from "../../services/api";
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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(Boolean(token));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function handleAuthenticationExpired(event: Event) {
      const expiredToken = (event as CustomEvent<{ token?: string }>).detail?.token;
      if (expiredToken && token && expiredToken !== token) return;
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setUser(null);
      setLoading(false);
      setError("Your session has expired. Please sign in again.");
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthenticationExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthenticationExpired);
  }, [token]);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    getCurrentUser(token)
      .then(setUser)
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, [token]);

  async function login(email: string, password: string) {
    setError(null);
    try {
      const response = await loginRequest(email, password);
      localStorage.setItem(TOKEN_KEY, response.access_token);
      setToken(response.access_token);
      setUser(await getCurrentUser(response.access_token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Authentication failed");
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setUser(null);
      throw reason;
    }
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }

  return <AuthContext.Provider value={{ user, token, loading, error, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
