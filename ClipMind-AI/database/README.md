# Database Workspace

This directory holds PostgreSQL documentation and reserved locations for future migration and seed scripts. The active SQLAlchemy models are in `backend/app/models` and are documented in [docs/database/README.md](../docs/database/README.md).

Module 1 does not include an Alembic migration runner or production seed command. Configure an empty PostgreSQL database through the backend environment variables and use the project team's schema setup procedure before starting the API. Backend tests create isolated SQLite tables automatically.
