import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../features/auth/AuthContext";
import type { Role } from "../types/auth";

interface ProtectedRouteProps {
  allowedRoles?: Role[];
}

export function ProtectedRoute({ allowedRoles }: ProtectedRouteProps) {
  const { user, loading } = useAuth();
  if (loading) return <div className="screen-state">Restoring your workspace...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />;
  }
  return <Outlet />;
}
