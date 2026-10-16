import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthProvider } from "./features/auth/AuthContext";
import { AnalyticsPage, Dashboard, DashboardRedirect, Login, MCQQuizPage, ProcessingStatusPage, Profile, Register, RoleFeaturePage, UploadHistoryPage, VideoKeyMomentsPage, VideoLibraryPage, VideoResultsPage, VideoSummaryPage, VideoUploadPage } from "./pages";
import { AdminUsersPage, AdminRolesPage, AdminMonitoringPage } from "./pages";
import "./styles/global.css";
import "./styles/modals.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route path="/dashboard" element={<DashboardRedirect />} />
              
              {/* Add this generic route to catch the sidebar link! */}
              <Route path="/analytics" element={<AnalyticsPage />} />

              <Route element={<ProtectedRoute allowedRoles={["Content Creator"]} />}>
                <Route path="/dashboard/content-creator" element={<Dashboard />} />
                <Route path="/creator/analytics" element={<AnalyticsPage />} />
                <Route path="/creator/upload" element={<VideoUploadPage />} />
                <Route path="/creator/videos" element={<VideoLibraryPage heading="Manage videos" description="Review the videos you have uploaded and their current processing state." />} />
                <Route path="/creator/transcripts" element={<VideoLibraryPage heading="Video transcripts" description="Generate, review, edit, and download transcripts for your videos." />} />
                <Route path="/creator/mcqs" element={<MCQQuizPage />} />
                <Route path="/creator/transcripts/:videoId" element={<VideoResultsPage />} />
                <Route path="/creator/summaries/:videoId" element={<VideoSummaryPage />} />
                <Route path="/creator/key-moments/:videoId" element={<VideoKeyMomentsPage />} />
                <Route path="/creator/history" element={<UploadHistoryPage />} />
                  <Route path="/creator/processing" element={<ProcessingStatusPage />} />
              </Route>
              {/* --- ADD THESE EDUCATOR ROUTES --- */}
              <Route element={<ProtectedRoute allowedRoles={["Educator"]} />}>
                <Route path="/dashboard/educator" element={<Dashboard />} />
                <Route path="/educator/upload" element={<VideoUploadPage />} />
                <Route path="/educator/transcripts" element={<VideoLibraryPage heading="Lecture Transcripts" description="Generate and review transcripts for your lecture videos." />} />
                <Route path="/educator/transcripts/:videoId" element={<VideoResultsPage />} />
                {/* These use the RoleFeaturePage to show the "Not Implemented" or "Checking Access" UI */}
                <Route path="/educator/classroom" element={<RoleFeaturePage title="Learning Materials" description="Keep lessons in one place" endpoint="/rbac/educator/content" />} />
                <Route path="/educator/content" element={<RoleFeaturePage title="Educational Content" description="Review your teaching shelf" endpoint="/rbac/educator/content" />} />
              </Route>

              {/* --- ADD THESE LEARNER ROUTES --- */}
              <Route element={<ProtectedRoute allowedRoles={["Learner"]} />}>
                <Route path="/dashboard/learner" element={<Dashboard />} />
                <Route path="/learner/videos" element={<VideoLibraryPage heading="Learning Videos" description="Browse the content library." />} />
                <Route path="/learner/transcripts" element={<RoleFeaturePage title="Transcripts" description="Read generated transcripts" />} />
                <Route path="/learner/summaries" element={<RoleFeaturePage title="Summaries" description="Surface the most important ideas" />} />
                <Route path="/learner/content" element={<RoleFeaturePage title="Learning Content" description="Open your learning shelf" endpoint="/rbac/learner/content" />} />
              </Route>

              {/* --- ADD THESE ADMINISTRATOR ROUTES --- */}
              <Route element={<ProtectedRoute allowedRoles={["Administrator"]} />}>
                <Route path="/dashboard/administrator" element={<Dashboard />} />
                <Route path="/admin/analytics" element={<AnalyticsPage />} />
                {/* Reuses the history page but with admin privileges to see ALL users' uploads */}
                <Route path="/admin/activity" element={<UploadHistoryPage administrator={true} />} />
                <Route path="/admin/users" element={<AdminUsersPage />} />
                <Route path="/admin/roles" element={<AdminRolesPage />} />
                <Route path="/admin/monitoring" element={<AdminMonitoringPage />} />
              </Route>

              <Route path="/profile" element={<Profile />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);