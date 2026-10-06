# Role based access and workflows

This document describes the current ClipMind implementation. A feature is marked complete only when it has a protected API and a usable frontend flow.

## Access model

JWTs identify a user. The backend reloads the user's role from the database for each authenticated request; frontend route guards only control navigation and are not a security boundary. Video operations are owner scoped for creators and educators. Learners can access completed videos shared with all learners or resources shared with a classroom they joined. Administrator operations require the Administrator role.

Public registration rejects the Administrator role. Administrators can change another user's role; they cannot change their own role. A role change is recorded in `audit_logs` and affects the next request because authorization reads the current database user.

## Workflow feature matrix

| Role | Feature | Backend | Frontend | Database | Authorization | Tests | Status |
|---|---|---|---|---|---|---|---|
| Content Creator | Upload, own-video management, transcript, summary, key moments, downloads, history, analytics with learner engagement | Complete | Complete | Persisted | Authenticated role; owner-scoped resources | Full backend suite; UI/API suites | Implemented |
| Learner | Browse/view shared videos, summaries, transcripts, key moments/timestamps, transcript search, learning history, bookmarks and bookmark navigation | Complete | Complete | Persisted | Share/classroom access; learner-owned history/bookmarks | Full backend suite; UI/API suites | Implemented |
| Educator | Lecture upload, educational summaries, transcript review/edit, summary sharing, material create/edit, classroom/resource/member management, learner access and engagement analytics | Complete | Complete | Persisted | Educator ownership plus classroom membership checks | Full backend suite; UI/API suites | Implemented |
| Administrator | Role management, platform activity/content, analytics, settings, processing jobs, audit logs and reports | Complete | Complete | Persisted | Administrator-only endpoints; self-role change denied | Full backend suite; UI/API suites | Implemented |
| Administrator | User activation/deletion | Partial | Partial | Users and roles persisted | Administrator-only listing and role changes | Role APIs covered | Partial: no activation/deletion |
| Administrator | Storage/resource utilization controls | Usage reporting only | Usage dashboard | File records persisted | Administrator-only | Admin API covered | Partial: no quotas/allocation controls |

## Persistence and endpoints

Existing video, transcript, summary, key moment, user, and processing tables are reused. Learning tables persist learner history and bookmarks, educator materials and summary shares, platform settings, audit events, classrooms, classroom membership, and classroom resources. Learning history records current playback position, watched seconds, and completion percentage.

Key endpoints include:

- Creator/educator video workflow: `/videos/*`, `/videos/{id}/transcript`, `/videos/{id}/summary`, `/videos/{id}/key-moments`, `/videos/{id}/topics`, and their download routes.
- Learners: `/learning/content`, `/learning/history`, `/learning/bookmarks`, `/learning/materials`, `/transcripts/search`, `/learner/classrooms/*`.
- Educators: `/educator/materials`, `/educator/shares`, `/educator/analytics`, `/educator/classrooms/*`.
- Administrators: `/admin/users`, `/admin/content`, `/admin/processing`, `/admin/storage`, `/admin/analytics`, `/admin/settings`, `/admin/audit-logs`, and `/admin/reports`.

## Database upgrades

The migration history now proceeds through the existing transcript/key-moment branch; the former duplicate-table branch is retained as a no-op compatibility revision. Fresh migration passed against a new local SQLite database through the latest classroom revision. Expected workflow tables, learner engagement columns, and cascade foreign keys were inspected. The hosted database has not been migrated, and an upgrade against an already-deployed PostgreSQL database was not exercised.

## Verification

Latest verification: backend full suite 208 passed; frontend 37 tests in 7 files passed; TypeScript typecheck and production build passed; fresh local SQLite migration/schema inspection passed. Classroom engagement excludes activity from nonmembers. Creator engagement is owner-scoped and uses saved learner history.

## Module 3 method and explainability

Topic regions use timestamped transcript segments as input. The local Sentence Transformer produces one embedding per segment; cosine similarity compares adjacent segments. A boundary is accepted only when the similarity falls below an adaptive transcript-relative cutoff and has corroborating evidence (a sharp local drop or sustained low similarity). Small regions are merged. If embeddings are unavailable, the fallback reports a single transcript-backed region rather than claiming unsupported semantic boundaries.

Each region exposes its source timestamps, source text, segment count, KeyBERT keyphrases with scores, and the count/average importance of overlapping persisted key moments. KeyBERT uses 1–3 word phrases and maximal marginal relevance (default diversity 0.5) to balance relevance and duplication. Key-moment topic labels combine those phrases with repeated transcript terms ranked by term frequency adjusted for inverse document frequency across timestamped segments. If KeyBERT cannot load, the deterministic fallback ranks transcript n-grams by frequency adjusted for phrase length; it does not invent phrase scores beyond normalized corpus frequency.

Key-moment importance is a documented heuristic: `0.45 × keyword coverage + 0.30 × content richness + 0.25 × topic fit`, clamped to `[0, 1]`. Candidate timestamps always come from the transcript, sentence context is expanded only within a topic, overlapping windows are suppressed, and selection is balanced across topic labels. These are explainable ranking signals, not calibrated probabilities or a claim of human-validated accuracy. Analytics are database-derived; they use persisted video/transcript/summary/key-moment data, and educator engagement uses learner playback history.
