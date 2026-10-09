ClipMind AI – Video Summarization Platform
An AI-powered platform for intelligent video analysis, transcription, and summarization. Built with FastAPI, React, and PostgreSQL. Designed for content creators, educators, and learners.

🎯 What It Does
ClipMind AI automates video content analysis:

Upload & Process – Upload videos and trigger automated analysis pipelines
Transcription – Extract accurate transcripts using OpenAI Whisper
AI Summaries – Generate concise, intelligent summaries of video content
Key Moments – Detect and highlight critical segments automatically
Role-Based Access – Support for Content Creators, Learners, Educators, and Admins
Analytics – Track processing metrics and user engagement
🛠️ Technology Stack
Component	Technology
Backend	FastAPI, Python 3.10+
Database	PostgreSQL with SQLAlchemy ORM
Frontend	React 18, Vite, TypeScript
Auth	JWT + bcrypt
AI Models	Whisper (transcription), Transformers, Sentence-Transformers
DevOps	Docker, Docker Compose
Language Composition:

Python: 50.7% | TypeScript: 33.4% | CSS: 15.6% | Other: 0.3%
📁 Project Structure
Code
backend/
├── app/
│   ├── routers/          # API endpoints (auth, video, transcript, summary, key_moment, admin, analytics)
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── services/         # Business logic (FFmpeg, AI processing)
│   ├── core/             # Config & security utilities
│   └── db/               # Database session management
├── requirements.txt
├── Dockerfile
└── .env.example

frontend/
├── app/                  # Main application entry
├── components/           # Reusable React components
├── lib/                  # Utilities & helpers
├── package.json
└── vite.config.ts

docs/
├── architecture.md
├── setup.md
└── api-reference.md

docker-compose.yml
🚀 Quick Start
Prerequisites
Docker & Docker Compose
Python 3.10+, Node.js 18+
Run Locally
bash
docker-compose up --build
Services start at:

Backend API: http://localhost:8000
Frontend: http://localhost:5173
Database: PostgreSQL on port 5432
Manual Setup
Backend:

bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Configure .env file
Frontend:

bash
cd frontend
npm install
npm run dev
🔌 Core API Endpoints
Method	Endpoint	Purpose
POST	/auth/register	User registration
POST	/auth/login	JWT token generation
POST	/videos/upload	Upload video for processing
GET	/videos	Retrieve user's video library
POST	/transcript/generate	Extract transcript from video
POST	/summary/generate	Generate AI summary
POST	/key-moment/detect	Identify key moments
GET	/analytics/stats	User & system metrics
GET	/admin/*	Admin management endpoints
🔐 Authentication & Authorization
Registration & Login – Email + password with bcrypt hashing
JWT Tokens – HS256-signed tokens with 30-minute expiration
Role-Based Access Control (RBAC) – Four roles: Content Creator, Learner, Educator, Administrator
Protected Routes – FastAPI dependency injection enforces auth on all secured endpoints
🧠 AI Processing Pipeline
Video Upload – User uploads video; stored and metadata recorded in PostgreSQL
Transcription – OpenAI Whisper extracts full transcript
Embedding & Analysis – Sentence-Transformers generate semantic embeddings
Summary Generation – Transformers-based abstractive summarization
Key Moment Detection – ML-driven identification of critical segments
Results Delivery – Processed data stored and returned via REST API
📊 Environment Configuration
Backend (.env)
env
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
DATABASE_URL=postgresql://user:password@host:5432/clipmind_db
Frontend (.env)
env
VITE_API_URL=http://127.0.0.1:8000
🎓 Features
✅ User Management – Registration, login, role assignment
✅ Video Upload & Storage – Local/cloud-based video persistence
✅ Automated Transcription – Whisper-based speech-to-text
✅ Intelligent Summaries – AI-generated content abstracts
✅ Key Moment Detection – Automatic segment identification
✅ Admin Dashboard – User & system management
✅ Analytics – Usage metrics and processing statistics
✅ Role-Based Dashboards – Customized views per user role

🏗️ Architecture
Code
┌─────────────────────────────────────┐
│     React Frontend (Vite)           │
│  - Login & Registration             │
│  - Video Upload Interface           │
│  - Results Dashboard                │
└──────────────┬──────────────────────┘
               │ REST API (JSON)
┌──────────────▼──────────────────────┐
│     FastAPI Backend                 │
│  - JWT Authentication               │
│  - Request Validation (Pydantic)    │
│  - AI Pipeline Orchestration        │
└──────────────┬──────────────────────┘
               │ SQLAlchemy ORM
┌──────────────▼──────────────────────┐
│    PostgreSQL Database              │
│  - Users, Videos, Transcripts       │
│  - Summaries, Key Moments           │
│  - Analytics Data                   │
└─────────────────────────────────────┘
📈 Performance & Scalability
Modular Architecture – Each AI task (transcription, summarization) is independently scalable
Database Indexing – Optimized queries on user, video, and metadata tables
Containerized Deployment – Docker enables consistent environments and easy horizontal scaling
JWT-Based Stateless Auth – No session storage; scales horizontally without session replication
🤝 Contributing
Organized by feature area:

Backend: FastAPI routes, SQLAlchemy models, AI service integrations
Frontend: React components, UI/UX, API client logic
Docs: Architecture, API specs, deployment guides
DevOps: Docker, environment configs, CI/CD pipelines
📝 License
See LICENSE file in repository (if present).

🚦 Current Status
Module 1 Complete:

✅ User authentication system
✅ Role-based access control
✅ Video management API
✅ Database schema & ORM models
✅ Admin & analytics routes
In Development / Planned:

Whisper transcription integration
Summary generation pipeline
Key moment detection algorithms
Frontend dashboard completion
