# ClipMind AI - Module 1 Architecture

This document outlines the system architecture for Module 1 of the ClipMind AI project. It reflects the **current state of the implementation** in the repository.

---

## 1. System Architecture

The current architecture is a classic decoupled client-server model:
- **Frontend**: [PLANNED] A React/Next.js client interface.
- **Backend**: A FastAPI REST API handling routing, validation, and authentication.
- **Database**: PostgreSQL (hosted on Supabase) accessed via SQLAlchemy ORM.

### Flow Diagram
```mermaid
flowchart TD
    A[Frontend Client (PLANNED)] -->|HTTPS / REST| B(FastAPI Backend)
    B -->|SQLAlchemy / psycopg2| C[(PostgreSQL Database)]
    B -->|FFmpeg Service| D[Video Processing (PLANNED)]
```

---

## 2. Frontend → FastAPI → PostgreSQL Flow

1. **Frontend Request**: The (PLANNED) frontend makes HTTP requests to the backend containing JSON payloads or multipart form data.
2. **FastAPI Validation**: Pydantic schemas validate the incoming data (e.g., ensuring emails are valid, passwords exist).
3. **Database Session**: A SQLAlchemy session (`get_db`) is yielded for the lifetime of the request.
4. **PostgreSQL Execution**: The backend executes SQL transactions via SQLAlchemy models (e.g., querying the `users` table).
5. **Response**: FastAPI serializes the SQLAlchemy models back to JSON and returns them to the frontend.

---

## 3. Authentication Flow

Authentication is handled via **JSON Web Tokens (JWT)** and **bcrypt** password hashing. 
The system adheres to a strict "Database-as-the-source-of-truth" paradigm for authorization.

### 4. Registration API
- **Endpoint**: `POST /auth/register`
- **Behavior**: 
  - Validates `email`, `name`, `password`, and `role` via Pydantic (`UserCreate` schema).
  - Checks PostgreSQL for duplicate emails.
  - Hashes the plaintext password using `bcrypt`.
  - Persists the new User to PostgreSQL and returns the created user (sans password).

### 5. Login API
- **Endpoint**: `POST /auth/login`
- **Behavior**:
  - Accepts standard JSON payload (`UserLogin` schema containing `email` and `password`).
  - Looks up the user in PostgreSQL.
  - Verifies the password hash using `bcrypt`.
  - Generates an expiring JWT.

### 6. JWT Authentication
- **Token Structure**: The JWT payload contains only the `sub` claim (the user's Database ID) and an `exp` claim (expiration time).
- **Security**: The token is signed using HS256 with the secret key (`SECRET_KEY` loaded from `.env`).

### 7. `get_current_user()`
- **Dependency**: Used to protect backend routes.
- **Behavior**: 
  - Extracts the Bearer token from the `Authorization` header.
  - Decodes and validates the JWT.
  - Extracts the user ID from the `sub` claim.
  - Queries PostgreSQL to ensure the user still exists and returns the SQLAlchemy `User` object.

### 8. Role-Based Access Control (RBAC)
- **Roles**: `Content Creator`, `Learner`, `Educator`, `Administrator`
- **Dependency**: `require_role(allowed_roles=[...])`
- **Behavior**: Evaluates the role directly from the freshly queried PostgreSQL `User` object (not from a stale JWT claim). 
- **Error Handling**: Returns `401 Unauthorized` for missing/invalid tokens, and `403 Forbidden` if the user's role is not in the allowed list.

---

## 9. PostgreSQL Database

### `User` Model
The database currently implements the following SQLAlchemy model:

| Field | Type | Attributes |
| :--- | :--- | :--- |
| `id` | Integer | Primary Key, Index |
| `name` | String | Not Null |
| `email` | String | Unique, Index, Not Null |
| `password` | String | Not Null (Bcrypt Hash) |
| `role` | String | Not Null (Lowercase), Default: `"learner"` |
| `created_at` | DateTime | Timezone Aware, Default: `now()` |

---

## 10. Planned Components

The following components are required for Module 1 but are **NOT YET IMPLEMENTED**:

- **[PLANNED] Video SQLAlchemy Model**: A database table to store video metadata, processing status, and a foreign key to the `User` model.
- **[PLANNED] `POST /videos/upload` API**: A protected endpoint to accept binary video files, store them locally/remotely, and create a video database record.
- **[PLANNED] FFmpeg Service**: A background task or service (`ffmpeg_service.py`) that compresses/processes the uploaded video and updates the database processing status.
- **[PLANNED] Frontend Web App**: The actual React/Next.js user interface to consume the APIs created above.
