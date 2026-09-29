import { NavLink, Outlet } from "react-router-dom";
import { BarChart3, BookOpen, Film, LayoutDashboard, LogOut, MonitorCog, ShieldCheck, Upload, UserRound, Users, FolderKanban, FileText, History, Sparkles } from "lucide-react";
import { useAuth } from "../features/auth/AuthContext";
import type { Role } from "../types/auth";

const roleNavigation: Record<Role, { label: string; path: string; icon: typeof Film }[]> = {
  "Content Creator": [
    { label: "Upload Video", path: "/creator/upload", icon: Upload },
    { label: "Transcripts", path: "/creator/transcripts", icon: FileText },
    { label: "MCQ Quiz", path: "/creator/mcqs", icon: BookOpen },
    { label: "Upload History", path: "/creator/history", icon: History },
    { label: "Analytics", path: "/analytics", icon: BarChart3 },
  ],
  Learner: [
    { label: "Videos", path: "/learner/videos", icon: Film },
    { label: "Transcripts", path: "/learner/transcripts", icon: FileText },
    { label: "Summaries", path: "/learner/summaries", icon: Sparkles },
    { label: "Learning Content", path: "/learner/content", icon: BookOpen },
  ],
  Educator: [
    { label: "Lecture Videos", path: "/educator/content", icon: Film },
    { label: "Transcripts", path: "/educator/transcripts", icon: FileText },
    { label: "Summaries", path: "/educator/content", icon: Sparkles },
    { label: "Learning Materials", path: "/educator/classroom", icon: BookOpen },
  ],
  Administrator: [
    { label: "Analytics", path: "/analytics", icon: BarChart3 },
    { label: "Users", path: "/admin/users", icon: Users },
    { label: "Roles", path: "/admin/roles", icon: ShieldCheck },
    { label: "Content", path: "/admin/activity", icon: FolderKanban },
    { label: "AI Processing", path: "/admin/monitoring", icon: MonitorCog },
  ],
};

export function AppShell() {
  const { user, logout } = useAuth();
  if (!user) return null;

  const initials = user.full_name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0]?.toUpperCase() ?? "")
    .join("") || "C";

  const dashboardPath = `/dashboard/${user.role.toLowerCase().replace(" ", "-")}`;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-wrap">
          <div className="brand">
            <span className="brand-mark"><Film size={18} /></span>
            <span className="brand-copy">ClipMind <em>AI</em></span>
          </div>
        </div>

        <div className="identity">
          <div className="identity-header">
            <div className="user-avatar" aria-label={`${user.full_name} avatar`}>{initials}</div>
            <div className="identity-copy">
              <strong>{user.full_name}</strong>
              <span className="role-badge">{user.role}</span>
            </div>
          </div>
        </div>

        <nav className="nav-list" aria-label="Sidebar navigation">
          <div className="nav-section-label">Main</div>
          <NavLink to={dashboardPath} className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
            <LayoutDashboard size={17} />
            <span>Dashboard</span>
          </NavLink>
          {roleNavigation[user.role].map(({ label, path, icon: Icon }) => (
            <NavLink key={path} to={path} className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
              <Icon size={17} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="nav-section-label">Account</div>
          <NavLink to="/profile" className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
            <UserRound size={17} />
            <span>Profile</span>
          </NavLink>
          <button className="logout" type="button" onClick={logout}>
            <LogOut size={17} />
            <span>Sign out</span>
          </button>
        </div>
      </aside>
      <main className="main-content"><Outlet /></main>
    </div>
  );
}
