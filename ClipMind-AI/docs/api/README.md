# API Documentation

Document FastAPI endpoints, request schemas, response schemas, authentication requirements, authorization rules, and error responses here.

## Module 1 registration

`POST /auth/register`

Request fields:

- `full_name`
- `email`
- `password`
- `confirm_password`
- `role`

Allowed role values are `Content Creator`, `Learner`, `Educator`, and `Administrator`.

Responses:

- `201 Created`: account created
- `409 Conflict`: email already registered
- `422 Unprocessable Entity`: missing, malformed, or inconsistent fields

Plain-text passwords and password hashes are never returned by the API.

## Login and protected requests

`POST /auth/login` accepts `email` and `password` and returns a bearer access token. The token includes the user ID, email, role, token type, and expiration. It does not include password data.

Send the token to protected endpoints using:

```text
Authorization: Bearer <access_token>
```

`GET /auth/me` is the Module 1 protected test endpoint. Missing, malformed, invalid, expired, or unknown-user tokens return `401 Unauthorized`.

The Postman collection [ClipMind-Registration.postman_collection.json](ClipMind-Registration.postman_collection.json) includes registration, login, and protected current-user requests.

## Role-based access control

RBAC reads the authenticated user's role through the `users.role_id` relationship. The JWT role claim is informational; authorization uses the current database role, so role changes take effect on subsequent requests.

| Role | Permissions |
|---|---|
| Content Creator | Upload videos, manage uploaded videos, view upload history |
| Learner | View available content, access learner-related content |
| Educator | Upload lecture videos, manage educational content |
| Administrator | Manage users, manage roles, monitor platform activity, manage uploaded content, access administrative functionality |

Example verification endpoints:

- `GET /rbac/creator/uploads`
- `GET /rbac/creator/history`
- `GET /rbac/learner/content`
- `GET /rbac/educator/content`
- `GET /rbac/admin/users`
- `GET /rbac/admin/platform`

## Video upload history

Upload and processing events are stored in `upload_history` and linked to their `videos` record. Each history response includes the video ID and filename, status, timestamp, event notes, and owner information.

- `GET /videos/history`: Content Creators receive events only for videos they own. Requires `view_upload_history`.
- `GET /admin/upload-history`: Administrators receive recent upload activity across the platform. Requires `monitor_platform_activity`.

Both endpoints accept an optional `limit` query parameter from `1` to `500`, return newest events first, and return `401 Unauthorized` for unauthenticated requests or `403 Forbidden` when the role lacks the required permission.

## Video processing status

`GET /videos/status` returns current status for videos owned by a Content Creator, Educator, or Administrator. Administrators receive platform-wide status visibility; other permitted users receive only their own videos.

`PATCH /videos/{video_id}/status` updates a status and records a matching upload-history event. Supported lifecycle transitions are `UPLOADED -> PROCESSING -> COMPLETED` or `FAILED`; a failed video may be retried with `FAILED -> PROCESSING`. Invalid transitions return `409 Conflict`, and unauthorized ownership attempts return `403 Forbidden`.

`POST /videos/{video_id}/process` runs the basic FFmpeg pipeline for an authorized owner or administrator. It downloads the private cloud object, extracts technical duration metadata, validates the media, and records `COMPLETED` or `FAILED`. Reprocessing a completed or already-processing video returns `409 Conflict`; processing failures return `422 Unprocessable Content` after recording the failed status.

## Video library

`GET /videos/` returns safe video metadata for the authenticated role. Content Creators and Educators see videos they own, Learners see completed videos available to them, and Administrators see platform-wide videos. Storage keys and cloud credentials are never returned. The endpoint accepts `limit` from `1` to `500` and requires a role permission; missing authentication returns `401 Unauthorized`.

## Module 1 Postman test matrix

Import [ClipMind-Registration.postman_collection.json](ClipMind-Registration.postman_collection.json) into Postman. Set `baseUrl`, `uploadFile`, `invalidFile`, and `oversizedFile` collection variables. The login requests expect role accounts matching the example emails, or replace those bodies with accounts created by the registration request. Run the valid login requests before protected requests so their test scripts populate `creatorToken`, `adminToken`, `learnerToken`, and `accessToken`; run valid upload before the processing-failure request so `videoId` is populated.

| Area | Method and endpoint | Authentication | Positive result | Negative coverage |
|---|---|---|---|---|
| Registration | `POST /auth/register` | None | `201 Created` | Duplicate email `409`; invalid password confirmation `422` |
| Login | `POST /auth/login` | None | `200 OK` with bearer JWT | Wrong credentials `401` |
| Current user | `GET /auth/me` | Bearer JWT | `200 OK` safe user profile | Missing/invalid JWT `401` |
| RBAC | `GET /rbac/{area}` | Bearer JWT | `200 OK` for permitted role | Unauthorized role `403` |
| Upload | `POST /videos/upload` multipart `file` | Creator/Educator/Admin JWT | `201 Created` metadata | Invalid file `400`; oversized file `413`; cloud failure `502` |
| Video list | `GET /videos/?limit=100` | Role JWT | `200 OK` array | Missing JWT `401`; unsupported permission `403` |
| Upload history | `GET /videos/history` or `GET /admin/upload-history` | Creator/Admin JWT | `200 OK` authorized events | Wrong role `403` |
| Processing status | `GET /videos/status` | Creator/Educator/Admin JWT | `200 OK` current states | Missing JWT `401` |
| FFmpeg processing | `POST /videos/{video_id}/process` | Authorized owner/Admin JWT | `200 OK` with `COMPLETED` | Invalid media/FFmpeg failure `422`; invalid transition `409` |

All protected requests use `Authorization: Bearer {{token}}`. Backend authorization remains authoritative even when a request is sent manually from Postman. The upload and processing requests require configured S3 and FFmpeg/FFprobe services; the collection's invalid and oversized file variables must point to real local fixtures.

Unauthenticated requests return `401 Unauthorized`. Authenticated users without the required permission return `403 Forbidden`.
## Module 3 transcript, summary, and key moments

Transcript generation uses the locally installed OpenAI Whisper model configured by `WHISPER_MODEL` (default `base`). FFmpeg normalizes non-audio uploads to mono, 16 kHz WAV before Whisper runs. The single `transcripts` record stores the full text and timestamped JSON segments; generation failures are stored with `FAILED` status and an error message. A duplicate request while a transcript is `PROCESSING` returns `409 Conflict`.

- `POST /videos/{video_id}/transcript`: generate and persist the transcript.
- `GET /videos/{video_id}/transcript`: return status, language, text, and `{start_time, end_time, text}` segments.
- `PATCH /videos/{video_id}/transcript`: edit text and optionally replace segments.
- `GET /videos/{video_id}/transcript/download`: download completed transcript text.
- `POST /videos/{video_id}/summary`: generate a deterministic NLP summary from the stored transcript.
- `GET /videos/{video_id}/summary`: return overview, main points, takeaways, status, and error information.
- `POST /videos/{video_id}/key-moments` (canonical) and `/key-moments/generate` (compatibility alias): detect and store transcript-backed moments.
- `GET /videos/{video_id}/key-moments`: return stored moments with timestamps, topic, description, and normalized importance score.

Summary generation uses transcript sentence chunking and deterministic extraction; it does not claim to call a cloud LLM. Key moments use lexical topic-boundary detection, discourse/importance keywords, vocabulary richness, duration, and adjacent-topic change. `importance_score` is consistently normalized to `0.0` through `1.0`. The frontend's `Watch Moment` control seeks the existing HTML5 player to `start_time` and begins playback.
