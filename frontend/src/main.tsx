import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthProvider } from "./features/auth/AuthContext";
import { Dashboard, DashboardRedirect, Login, ProcessingStatusPage, Profile, Register, RoleFeaturePage, UploadHistoryPage, VideoLibraryPage, VideoUploadPage } from "./pages";
import "./styles/global.css";

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
              <Route element={<ProtectedRoute allowedRoles={["Content Creator"]} />}>
                <Route path="/dashboard/content-creator" element={<Dashboard />} />
                <Route path="/creator/upload" element={<VideoUploadPage />} />
                <Route path="/creator/videos" element={<VideoLibraryPage heading="Manage videos" description="Review the videos you have uploaded and their current processing state." />} />
                <Route path="/creator/transcripts" element={<VideoLibraryPage heading="Video transcripts" description="Generate, review, edit, and download transcripts for your videos." />} />
                <Route path="/creator/history" element={<UploadHistoryPage />} />
                <Route path="/creator/processing" element={<ProcessingStatusPage />} />
              </Route>
              <Route element={<ProtectedRoute allowedRoles={["Learner"]} />}>
                <Route path="/dashboard/learner" element={<Dashboard />} />
                <Route path="/learner/videos" element={<VideoLibraryPage heading="Available videos" description="Discover completed videos available for your learning path." />} />
                <Route path="/learner/content" element={<RoleFeaturePage title="Learning Content" description="Return to the lessons and materials in your learning shelf." endpoint="/rbac/learner/content" />} />
                <Route path="/learner/summaries" element={<RoleFeaturePage title="Summaries" description="AI-generated summaries will appear here when processing is enabled." />} />
                <Route path="/learner/transcripts" element={<VideoLibraryPage heading="Video transcripts" description="Read and search transcripts for completed videos available to your learning path." />} />
              </Route>
              <Route element={<ProtectedRoute allowedRoles={["Educator"]} />}>
                <Route path="/dashboard/educator" element={<Dashboard />} />
                <Route path="/educator/upload" element={<VideoUploadPage />} />
                <Route path="/educator/content" element={<VideoLibraryPage heading="Educational content" description="Review the lecture videos and educational materials you manage." />} />
                <Route path="/educator/transcripts" element={<VideoLibraryPage heading="Lecture transcripts" description="Generate, review, edit, and download transcripts for your lectures." />} />
                <Route path="/educator/classroom" element={<RoleFeaturePage title="Classroom Content" description="Keep classroom-ready lessons together for your learners." endpoint="/rbac/educator/content" />} />
              </Route>
              <Route element={<ProtectedRoute allowedRoles={["Administrator"]} />}>
                <Route path="/dashboard/administrator" element={<Dashboard />} />
                <Route path="/admin/users" element={<RoleFeaturePage title="Users" description="Review and manage platform accounts." endpoint="/rbac/admin/users" />} />
                <Route path="/admin/roles" element={<RoleFeaturePage title="Roles" description="Inspect the platform access structure." endpoint="/rbac/admin/users" />} />
                <Route path="/admin/activity" element={<UploadHistoryPage administrator />} />
                <Route path="/admin/monitoring" element={<RoleFeaturePage title="System Monitoring" description="Check service readiness and platform health." endpoint="/rbac/admin/platform" />} />
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
