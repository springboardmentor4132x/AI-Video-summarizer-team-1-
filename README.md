<div align="center">

# 🎬 ClipMind AI

### Intelligent Video Summarization & Key Moments Platform

**Transcribe. Summarize. Discover the moments that matter.**

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React_18-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)

[Features](#-features) • [Quick Start](#-quick-start) • [Pipeline](#-ai-processing-pipeline) • [API](#-core-api-endpoints) • [Architecture](#-architecture) • [Status](#-project-status)

</div>

---

## 📖 Overview

**ClipMind AI** is an AI-powered platform that turns long videos into something you can read, search and jump around in. Upload a video (or paste a YouTube link) and ClipMind produces a **timestamped transcript**, **short and detailed summaries**, **topics and key moments with highlight clips**, **analytics** and **practice MCQs**.

It is built with **FastAPI**, **React** and **PostgreSQL**, and is designed for **content creators**, **educators**, **learners** and **administrators**.

> 💡 **Why ClipMind?** Stop scrubbing through hours of footage. Click a key moment and the video jumps straight to it.

---

## 🎯 Features

| | Capability | Description |
|---|---|---|
| 📤 | **Upload and YouTube import** | Upload mp4, mov, avi, mkv or webm (up to 500 MB), or paste a YouTube URL |
| 🎞️ | **FFmpeg processing** | Videos are converted to H.264 + AAC; audio is extracted as 16 kHz mono WAV |
| 📝 | **Transcription** | Local **OpenAI Whisper** (base) with language detection and timestamped segments |
| 🤖 | **AI summaries** | **BART-large-CNN** hierarchical summarization: short and detailed summaries, with quality checks |
| ⭐ | **Key moments and topics** | Sentence embeddings, cosine similarity, topic segmentation and importance scoring |
| ✂️ | **Highlight clips** | FFmpeg cuts a clip for every key moment |
| ▶️ | **Timestamp seeking** | Click a moment and the player starts from that point |
| ❓ | **MCQ quiz** | Practice questions for processed videos |
| 📊 | **Analytics** | Creator and administrator dashboards built from real database data, keywords and insights |
| 🔐 | **Role-based access** | Content Creator, Learner, Educator and Administrator |

---

## 🛠️ Technology Stack

| Component | Technology |
|:---|:---|
| **Backend** | `FastAPI`, `Python 3.10+`, `SQLAlchemy`, `Alembic` |
| **Database** | `PostgreSQL` |
| **Frontend** | `React 18`, `Vite`, `TypeScript` |
| **Auth** | `JWT` + password hashing |
| **Speech-to-text** | `OpenAI Whisper` (base, runs locally) |
| **Summarization** | `Hugging Face Transformers`, `facebook/bart-large-cnn` |
| **Embeddings** | `Sentence-Transformers`, `all-MiniLM-L6-v2` |
| **Video / audio** | `FFmpeg`, `yt-dlp` (YouTube download) |
| **DevOps** | `Docker`, `Docker Compose` |

---

## 📁 Project Structure

```text
clipmind-ai/
├── backend/
│   ├── app/
│   │   ├── routers/      # auth, video, transcript, summary, key moments, analytics, rbac
│   │   ├── models/       # SQLAlchemy models (User, Video, Transcript, Summary, KeyMoment)
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── services/     # ffmpeg, transcription, summarization, embedding,
│   │   │                 # key moment, highlight services
│   │   ├── core/         # configuration and security
│   │   └── db/           # database session
│   ├── alembic/          # database migrations
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── components/   # AppShell, ProtectedRoute, shared UI
│   │   ├── features/     # auth context and feature modules
│   │   ├── pages/        # dashboards, upload, transcript, summary, key moments, analytics, MCQ
│   │   ├── styles/
│   │   └── types/
│   ├── package.json
│   └── vite.config.ts
│
├── docs/                 # architecture, setup, API notes, milestone reports
└── docker-compose.yml
```

---

## 🚀 Quick Start

### ✅ Prerequisites

- 🐳 **Docker** and **Docker Compose**
- 💾 About **4 GB of free RAM** for the AI models (Whisper and BART run locally)
- *(Manual setup only)* 🐍 Python `3.10+`, 🟢 Node.js `18+`, FFmpeg

### ⚡ Run with Docker (recommended)

```bash
docker compose up --build
```

| Service | URL |
|:---|:---|
| 🔧 **Backend API** | http://localhost:8000 |
| 📚 **API docs (Swagger)** | http://localhost:8000/docs |
| 🖥️ **Frontend** | http://localhost:5173 |

> The first run downloads the AI models, so it can take a few minutes.

### 🔨 Manual Setup

<details>
<summary><b>🐍 Backend</b></summary>

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then edit the values
alembic upgrade head             # create or update the database tables
uvicorn app.main:app --reload
```

</details>

<details>
<summary><b>⚛️ Frontend</b></summary>

```bash
cd frontend
npm install
npm run dev
```

</details>

---

## ⚙️ Environment Configuration

**Backend** — `backend/.env`

```env
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
DATABASE_URL=postgresql://user:password@host:5432/clipmind_db

# Optional AI settings (defaults shown)
WHISPER_MODEL=base
LOCAL_SUMMARY_MODEL=facebook/bart-large-cnn
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

**Frontend** — `frontend/.env`

```env
VITE_API_URL=http://127.0.0.1:8000
```

> ⚠️ **Security:** never commit your real `.env` file. Use a long random `SECRET_KEY`, for example `openssl rand -hex 32`.

---

## 🧠 AI Processing Pipeline

```mermaid
flowchart TD
    A["Upload video or YouTube URL"] --> B["Validate and save file"]
    B --> C["FFmpeg: convert to H.264 and AAC"]
    C --> D["FFmpeg: extract 16 kHz mono audio"]
    D --> E["Whisper: timestamped transcript"]
    E --> F[("PostgreSQL")]
    F --> G["BART: short and detailed summary"]
    F --> H["Embeddings and cosine similarity"]
    H --> I["Topic segmentation"]
    I --> J["Importance scoring"]
    J --> K["Key moments"]
    K --> L["FFmpeg: highlight clips"]
    G --> M["React frontend"]
    L --> M
    F --> N["Analytics dashboards"]
    N --> M
```

**One transcript, many features.** Whisper runs once. The summary, key moments, analytics and MCQs all reuse the stored transcript, so nothing is processed twice.

1. **Upload** — file or YouTube link; the video record is saved in PostgreSQL.
2. **FFmpeg** — the video is converted to H.264 and AAC; audio is extracted for speech recognition.
3. **Transcription** — local Whisper returns text, language and timestamped segments.
4. **Summarization** — BART summarizes long transcripts in chunks, then combines the notes into a short and a detailed summary.
5. **Key moments** — each transcript segment is embedded; drops in similarity between neighbours mark topic changes; segments are scored (keyword coverage 45%, content richness 30%, topic fit 25%); the best segment per topic is kept, expanded to sentence boundaries, and overlaps are removed.
6. **Highlights** — FFmpeg cuts a clip for each key moment.
7. **Display** — the frontend shows transcript, summaries, topics, key moments and analytics, with click-to-seek.

### Processing status

```mermaid
stateDiagram-v2
    [*] --> uploaded
    uploaded --> processing
    processing --> completed
    processing --> failed
    failed --> processing : retry
    completed --> [*]
```

Transcripts and summaries use the statuses `PENDING`, `PROCESSING`, `COMPLETED` and `FAILED`. If summarization fails, the transcript is kept and the summary can be retried.

---

## 🔌 Core API Endpoints

Full interactive documentation is available at `/docs` when the backend is running.

| Method | Endpoint | Purpose |
|:---:|:---|:---|
| ![POST](https://img.shields.io/badge/POST-49cc90?style=flat-square) | `/auth/register` | Register a user |
| ![POST](https://img.shields.io/badge/POST-49cc90?style=flat-square) | `/auth/login` | Log in and receive a JWT |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/auth/me` | Current user |
| ![POST](https://img.shields.io/badge/POST-49cc90?style=flat-square) | `/videos/upload` | Upload a video |
| ![POST](https://img.shields.io/badge/POST-49cc90?style=flat-square) | `/videos/youtube` | Import a video from a YouTube URL |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/videos` | The user's video library |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/videos/{id}/status` | Processing status |
| ![POST](https://img.shields.io/badge/POST-49cc90?style=flat-square) | `/videos/{id}/transcript` | Start transcript generation |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/videos/{id}/transcript` | Transcript, language, segments, status |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/videos/{id}/transcript/download` | Download the transcript |
| ![POST](https://img.shields.io/badge/POST-49cc90?style=flat-square) | `/videos/{id}/key-moments/generate` | Detect key moments from the transcript |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/videos/{id}/key-moments` | Key moments with start and end time |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/videos/{id}/highlights/{moment_id}` | Highlight clip for a moment |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/videos/{id}/mcqs` | MCQ questions for a video |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | Analytics endpoints | Creator and administrator dashboards |

Summary endpoints follow the same pattern; see `/docs` for exact paths.

**Key moment response (example):**

```json
{
  "video_id": 5,
  "status": "completed",
  "key_moments": [
    {
      "id": 11,
      "start_time": 0.0,
      "end_time": 5.16,
      "title": "...",
      "topic": "Agents",
      "importance_score": 1,
      "text": "...",
      "highlight_path": "/videos/5/highlights/11"
    }
  ]
}
```

Times are in seconds, so the player can use them directly: `video.currentTime = start_time`.

---

## 🔐 Authentication & Roles

- 🔑 **Registration and login** with hashed passwords
- 🎟️ **JWT** tokens (`HS256`), sent as `Authorization: Bearer <token>`
- 🛡️ **Protected routes and APIs**; users can only access their own videos and results

| Role | Main access |
|:---|:---|
| **Content Creator** | Upload, manage videos, transcripts, summaries, key moments, MCQ quiz, upload history, analytics |
| **Educator** | Upload lectures, transcripts, key moments, learning materials |
| **Learner** | View available videos, transcripts, summaries and learning content |
| **Administrator** | Platform analytics, users, roles, content and processing overview |

---

## 🏗️ Architecture

```text
┌─────────────────────────────────────┐
│       React Frontend (Vite)         │
│  Login, Upload, Transcript, Summary │
│  Key Moments, Analytics, MCQ Quiz   │
└──────────────┬──────────────────────┘
               │ REST API (JSON + JWT)
┌──────────────▼──────────────────────┐
│          FastAPI Backend            │
│  Auth, validation, role checks      │
│  Background processing pipeline     │
├─────────────────────────────────────┤
│  FFmpeg   Whisper   BART            │
│  Sentence-Transformers   yt-dlp     │
└──────────────┬──────────────────────┘
               │ SQLAlchemy ORM
┌──────────────▼──────────────────────┐
│          PostgreSQL                 │
│  Users, Videos, Transcripts,        │
│  Summaries, Key Moments             │
└─────────────────────────────────────┘
```

**Data model:** `User → Video → Transcript → Summary`, and `Video → KeyMoment`.

---

## 🚦 Project Status

All four milestones are implemented.

| Milestone | Weeks | Scope | Status |
|:---|:---:|:---|:---:|
| **1** | 1–2 | Setup, authentication, role-based access, video upload, FFmpeg processing | ✅ |
| **2** | 3–4 | Whisper transcripts, BART summaries, statuses, retry | ✅ |
| **3** | 5–6 | Topics, key moments, highlight clips, analytics | ✅ |
| **4** | 7–8 | YouTube import, MCQ quiz, integration and testing | ✅ |

### ⚠️ Known limitations

- Whisper and BART run on the server CPU, so long videos take time and need enough RAM (about 4 GB).
- Transcript accuracy drops with noisy audio or several speakers.
- Summaries are abstractive and may occasionally change a detail.
- YouTube downloads can be blocked on some cloud servers; file upload always works.
- Analytics topics are based on frequent words, not yet on key-moment topics.

### 🔭 Future work

Multilingual support, speaker identification, chat with a video, semantic checking of summaries, GPU processing.

---

## 🤝 Contributing

- Never commit directly to `main`. Create a feature branch and open a Pull Request.
- Keep secrets out of Git (`.env` is ignored).
- Run the backend tests before opening a Pull Request.

| Area | Scope |
|:---|:---|
| 🐍 **Backend** | Routes, models, migrations, AI services |
| ⚛️ **Frontend** | Components, pages, API client |
| 📚 **Docs** | Architecture, API notes, milestone reports |
| 🐳 **DevOps** | Docker, environment configuration |

---

## 📝 License

See the `LICENSE` file in the repository *(if present)*.

<div align="center">

**Built by Team 1 for creators, educators and learners**

</div>
