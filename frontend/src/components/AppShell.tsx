import { NavLink, Outlet } from "react-router-dom";
import { BookOpen, Gauge, LayoutDashboard, Library, LogOut, MonitorCog, ShieldCheck, Upload, UserRound, Users, Video } from "lucide-react";
import { useAuth } from "../features/auth/AuthContext";
import type { Role } from "../types/auth";

const roleNavigation: Record<Role, { label: string; path: string; icon: typeof Video }[]> = {
  "Content Creator": [
    { label: "Upload Video", path: "/creator/upload", icon: Upload },
    { label: "Manage Videos", path: "/creator/videos", icon: Video },
    { label: "Transcripts", path: "/creator/transcripts", icon: Library },
    { label: "Upload History", path: "/creator/history", icon: Library },
    { label: "Processing Status", path: "/creator/processing", icon: Gauge },
  ],
  Learner: [
    { label: "Available Videos", path: "/learner/videos", icon: Video },
    { label: "Learning Content", path: "/learner/content", icon: BookOpen },
    { label: "Summaries", path: "/learner/summaries", icon: Library },
    { label: "Transcripts", path: "/learner/transcripts", icon: Library },
  ],
  Educator: [
    { label: "Upload Lecture", path: "/educator/upload", icon: Upload },
    { label: "Educational Content", path: "/educator/content", icon: Library },
    { label: "Transcripts", path: "/educator/transcripts", icon: Library },
    { label: "Classroom Content", path: "/educator/classroom", icon: BookOpen },
  ],
  Administrator: [
    { label: "Users", path: "/admin/users", icon: Users },
    { label: "Roles", path: "/admin/roles", icon: ShieldCheck },
    { label: "Platform Activity", path: "/admin/activity", icon: MonitorCog },
    { label: "System Monitoring", path: "/admin/monitoring", icon: Gauge },
  ],
};

export function AppShell() {
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">C</span><span>ClipMind <em>AI</em></span></div>
        <div className="identity"><span className="eyebrow">SIGNED IN AS</span><strong>{user.full_name}</strong><span>{user.role}</span></div>
        <nav className="nav-list">
          <NavLink to={`/dashboard/${user.role.toLowerCase().replace(" ", "-")}`}><LayoutDashboard size={17} /> Dashboard</NavLink>
          {roleNavigation[user.role].map(({ label, path, icon: Icon }) => <NavLink key={path} to={path}><Icon size={17} /> {label}</NavLink>)}
          <NavLink to="/profile"><UserRound size={17} /> Profile</NavLink>
        </nav>
        <button className="logout" onClick={logout}><LogOut size={17} /> Sign out</button>
      </aside>
      <main className="main-content"><Outlet /></main>
    </div>
  );
}
