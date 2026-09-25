import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthProvider } from "./features/auth/AuthContext";
import { KeyMomentsPage } from "./features/key-moments/KeyMomentsPage";
import { AnalyticsPage, Dashboard, DashboardRedirect, Login, ProcessingStatusPage, Profile, Register, RoleFeaturePage, TranscriptLibraryPage, UploadHistoryPage, VideoDetailsPage, VideoLibraryPage, VideoUploadPage } from "./pages";
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
                <Route path="/creator/transcripts" element={<TranscriptLibraryPage heading="Video transcripts" description="Review transcript status and open transcripts for the videos you manage." />} />
                <Route path="/creator/transcripts/:videoId" element={<VideoDetailsPage transcriptOnly />} />
                <Route path="/creator/videos/:videoId" element={<VideoDetailsPage />} />
                <Route path="/creator/history" element={<UploadHistoryPage />} />
                <Route path="/creator/processing" element={<ProcessingStatusPage />} />
                <Route path="/creator/key-moments/:videoId" element={<KeyMomentsPage />} />
                <Route path="/analytics" element={<AnalyticsPage />} />
              </Route>
              <Route element={<ProtectedRoute allowedRoles={["Learner"]} />}>
                <Route path="/dashboard/learner" element={<Dashboard />} />
                <Route path="/learner/videos" element={<VideoLibraryPage heading="Available videos" description="Discover completed videos available for your learning path." />} />
                <Route path="/learner/content" element={<RoleFeaturePage title="Learning Content" description="Return to the lessons and materials in your learning shelf." endpoint="/rbac/learner/content" />} />
                <Route path="/learner/summaries" element={<RoleFeaturePage title="Summaries" description="AI-generated summaries will appear here when processing is enabled." />} />
                <Route path="/learner/transcripts" element={<TranscriptLibraryPage heading="Video transcripts" description="Read transcript status and open transcripts for videos available to your learning path." />} />
                <Route path="/learner/transcripts/:videoId" element={<VideoDetailsPage transcriptOnly />} />
                <Route path="/learner/videos/:videoId" element={<VideoDetailsPage />} />
                <Route path="/learner/key-moments/:videoId" element={<KeyMomentsPage />} />
              </Route>
              <Route element={<ProtectedRoute allowedRoles={["Educator"]} />}>
                <Route path="/dashboard/educator" element={<Dashboard />} />
                <Route path="/educator/upload" element={<VideoUploadPage />} />
                <Route path="/educator/content" element={<VideoLibraryPage heading="Educational content" description="Review the lecture videos and educational materials you manage." />} />
                <Route path="/educator/transcripts" element={<TranscriptLibraryPage heading="Lecture transcripts" description="Review transcript status and open transcripts for the lectures you manage." />} />
                <Route path="/educator/transcripts/:videoId" element={<VideoDetailsPage transcriptOnly />} />
                <Route path="/educator/videos/:videoId" element={<VideoDetailsPage />} />
                <Route path="/educator/classroom" element={<RoleFeaturePage title="Classroom Content" description="Keep classroom-ready lessons together for your learners." endpoint="/rbac/educator/content" />} />
                <Route path="/educator/key-moments/:videoId" element={<KeyMomentsPage />} />
              </Route>
              <Route element={<ProtectedRoute allowedRoles={["Administrator"]} />}>
                <Route path="/dashboard/administrator" element={<Dashboard />} />
                <Route path="/admin/users" element={<RoleFeaturePage title="Users" description="Review and manage platform accounts." endpoint="/rbac/admin/users" />} />
                <Route path="/admin/roles" element={<RoleFeaturePage title="Roles" description="Inspect the platform access structure." endpoint="/rbac/admin/users" />} />
                <Route path="/admin/activity" element={<UploadHistoryPage administrator />} />
                <Route path="/admin/monitoring" element={<RoleFeaturePage title="System Monitoring" description="Check service readiness and platform health." endpoint="/rbac/admin/platform" />} />
                <Route path="/admin/analytics" element={<AnalyticsPage />} />
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

