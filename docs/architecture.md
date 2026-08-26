# System Architecture (Module 1)

## Core Technology Stack
*   **Frontend:** Next.js (App Router), Tailwind CSS
*   **Backend:** Python FastAPI
*   **Database:** PostgreSQL (Relational Data & RBAC)
*   **Processing:** FFmpeg (Synchronous for Module 1, transitioning to Event-Driven later)

## Video Upload State Machine
To ensure data integrity between the API and the processing pipeline, the `Video` table must adhere strictly to these states:
1.  `pending_upload`: File is being transferred.
2.  `uploaded`: File saved to disk/cloud, awaiting FFmpeg.
3.  `processing`: FFmpeg is currently extracting metadata/audio.
4.  `completed`: FFmpeg finished successfully.
5.  `failed`: An error occurred during validation or processing.

## Module 1 Data Flow
```mermaid
sequenceDiagram
    actor User (Creator/Admin)
    participant Frontend (Next.js)
    participant Backend (FastAPI)
    participant Database (PostgreSQL)
    participant Processor (FFmpeg)

    User->>Frontend: Upload Video File
    Frontend->>Backend: POST /api/v1/videos/upload (JWT)
    Backend->>Database: Create Record (status: 'pending_upload')
    Backend->>Backend: Validate File & Save to Storage
    Backend->>Database: Update Record (status: 'uploaded')
    Backend->>Processor: Trigger FFmpeg Processing
    Processor-->>Database: Update Record (status: 'processing')
    Processor-->>Processor: Extract Audio / Metadata
    Processor-->>Database: Update Record (status: 'completed' / 'failed')
    Processor-->>Backend: Return Process Result
    Backend-->>Frontend: 200 OK (Video Processed)
    Frontend-->>User: Display on Dashboard