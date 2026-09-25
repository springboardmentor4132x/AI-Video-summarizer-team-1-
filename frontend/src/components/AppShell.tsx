import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { 
  BarChart3, BookOpen, Film, LayoutDashboard, LogOut, 
  MonitorCog, ShieldCheck, Upload, UserRound, Users, 
  FolderKanban, FileText, History, Sparkles, Menu, X 
} from "lucide-react";
import { useAuth } from "../features/auth/AuthContext";
import type { Role } from "../types/auth";

const roleNavigation: Record<Role, { label: string; path: string; icon: typeof Film }[]> = {
  "Content Creator": [
    { label: "Upload Video", path: "/creator/upload", icon: Upload },
    { label: "Transcripts", path: "/creator/transcripts", icon: FileText },
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
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  if (!user) return null;

  const displayName = user.full_name || (user as any).name || "ClipMind User";
  
  const initials = displayName
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part: string) => part[0]?.toUpperCase() ?? "")
    .join("") || "C";

  const dashboardPath = `/dashboard/${user.role.toLowerCase().replace(" ", "-")}`;

  return (
    <div className="app-shell">
      <aside className={`sidebar ${isMobileMenuOpen ? "open" : ""}`}>
        
        <div className="sidebar-header">
          {/* Logo with Refresh Action */}
          <div 
            className="brand-wrap" 
            onClick={() => window.location.reload()} 
            role="button" 
            tabIndex={0}
            title="Refresh App"
          >
            <div className="brand">
              <span className="brand-mark"><Film size={18} /></span>
              <span className="brand-copy">ClipMind <em>AI</em></span>
            </div>
          </div>

          {/* Mobile Hamburger Toggle */}
          <button 
            className="mobile-toggle" 
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            aria-label="Toggle mobile menu"
          >
            {isMobileMenuOpen ? <X size={26} /> : <Menu size={26} />}
          </button>
        </div>

        {/* Collapsible Content */}
        <div className="sidebar-content">
          <div className="identity">
            <div className="identity-header">
              <div className="user-avatar" aria-label={`${displayName} avatar`}>{initials}</div>
              <div className="identity-copy">
                <strong>{displayName}</strong>
                <span className="role-badge">{user.role}</span>
              </div>
            </div>
          </div>

          <nav className="nav-list" aria-label="Sidebar navigation">
            <div className="nav-section-label">Main</div>
            <NavLink 
              to={dashboardPath} 
              onClick={() => setIsMobileMenuOpen(false)}
              className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
            >
              <LayoutDashboard size={17} />
              <span>Dashboard</span>
            </NavLink>
            
            {roleNavigation[user.role].map(({ label, path, icon: Icon }) => (
              <NavLink 
                key={path} 
                to={path} 
                onClick={() => setIsMobileMenuOpen(false)}
                className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
              >
                <Icon size={17} />
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="sidebar-footer">
            <div className="nav-section-label">Account</div>
            <NavLink 
              to="/profile" 
              onClick={() => setIsMobileMenuOpen(false)}
              className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
            >
              <UserRound size={17} />
              <span>Profile</span>
            </NavLink>
            <button 
              className="logout" 
              type="button" 
              onClick={() => { setIsMobileMenuOpen(false); logout(); }}
            >
              <LogOut size={17} />
              <span>Sign out</span>
            </button>
          </div>
        </div>

      </aside>
      <main className="main-content"><Outlet /></main>
    </div>
  );
}