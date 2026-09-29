# FastAPI Backend

The backend contains the FastAPI application and server-side boundaries for authentication, authorization, users, roles, videos, transcripts, upload history, PostgreSQL access, local/S3 storage, and FFmpeg coordination.

## Run locally

From this directory, create a virtual environment, install dependencies, and copy `.env.example` to `.env`. Replace every `DB_*` placeholder with the PostgreSQL connection values for your environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload
```

For local transcript generation, install Whisper and ensure FFmpeg is on `PATH`:

```powershell
python -m pip install openai-whisper
```

The first transcript generation downloads the configured Whisper model (`WHISPER_MODEL`, default `base`). If Whisper or FFmpeg is unavailable, generation returns a failed processing error and does not report success.

To test the PostgreSQL connection directly:

```powershell
python .\scripts\test_database_connection.py
```

The health endpoint is available at `http://127.0.0.1:8000/` and Swagger UI is available at `http://127.0.0.1:8000/docs`.

## Current scope

The backend contains authentication, role authorization, PostgreSQL metadata persistence, local/S3 video upload, video listing, transcript generation/editing/download, upload history, processing status, FFmpeg audio normalization, local Whisper transcription, deterministic transcript summarization, topic-aware key-moment detection, and normalized importance scoring.

## Cloud video storage

Video uploads use Amazon S3. Configure `S3_BUCKET`, `S3_REGION`, and optionally `S3_PREFIX` in `.env`. The backend accepts credentials through `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN`, but deployed environments should prefer an IAM role or standard AWS credential provider. Never commit `.env` or place credentials in source code.

The upload flow validates the multipart file, streams it through a temporary spool to a private S3 object with server-side AES-256 encryption, and then stores only the S3 object key plus metadata in PostgreSQL. If S3 fails, no `Video` record is created. If the database write fails after S3 succeeds, the backend attempts to delete the object. AI processing does not begin as part of upload.

## FFmpeg processing

Install `ffmpeg` and `ffprobe` on the backend host and ensure both are on `PATH`, or configure `FFMPEG_BINARY` and `FFPROBE_BINARY`. `POST /videos/{video_id}/process` downloads the stored object to a temporary file, extracts duration with FFprobe, validates the media with FFmpeg, and updates the video to `COMPLETED`. Failures update the video to `FAILED` and create an upload-history event. Transcript generation separately reuses the stored object for audio normalization and local Whisper processing.

## Registration endpoint

`POST /auth/register` accepts JSON with `full_name`, `email`, `password`, `confirm_password`, and one of the allowed roles: `Content Creator`, `Learner`, `Educator`, or `Administrator`.

In Postman, set the request body to `raw` JSON:

```json
{
	"full_name": "Asha Kumar",
	"email": "asha@example.com",
	"password": "strong-password",
	"confirm_password": "strong-password",
	"role": "Learner"
}
```

Successful registration returns HTTP `201`. Duplicate email returns `409`, and invalid fields return `422`. The response never includes the password or password hash.
Transcript generation reuses the same storage object and performs its own Whisper audio normalization through `app.services.speech_to_text`. Summary and key-moment routes consume the stored transcript and persist their results in the existing one-to-one summary and key-moment tables.
