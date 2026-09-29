# UI Documentation

Document the Module 1 page structure, role-based navigation, wireframes, and frontend conventions here.

Initial pages:


# ClipMind AI UI

## Frontend Structure

The Vite React app uses:

- `AuthProvider` for JWT restoration, login, logout, and current-user state.
- `ProtectedRoute` for authentication and role route guards.
- `AppShell` for role-specific navigation.
- `services/api.ts` for HTTP calls and typed API errors.
- `pages.tsx` for Module 1 route pages.

## Public Pages

- `/login`: login form and authentication errors.
- `/register`: account registration, role selection, password validation, and API validation feedback.

## Protected Pages

- `/dashboard`: redirects to the authenticated role dashboard.
- `/profile`: current account information.
- Creator: upload, video library, upload history, processing status.
- Learner: completed available videos and learning placeholders.
- Educator: lecture upload, educational video library, classroom placeholder.
- Administrator: users/roles placeholders, platform upload history, monitoring placeholder.

## Request States

Data pages provide loading, empty, success, retry, and error states. The API client preserves HTTP status codes through `ApiError`, while backend responses remain the final source of authorization decisions.

## Current UI Scope

The UI supports registration, login, role dashboards, video upload, video listing, history, and processing status. Summary, transcript, classroom management, and full administrator management interfaces are not implemented.
