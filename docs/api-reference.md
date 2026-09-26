# Transcript and summary downloads

Both routes require a bearer token and return an attachment as `text/plain`.
Ownership is checked against the authenticated user. Missing records return
404; records that exist but are not completed return 409.

| Method | Route | Response |
| --- | --- | --- |
| GET | `/videos/{video_id}/transcript/download` | `transcript.txt`, title and timestamped stored segments (or stored transcript text when segment data is unavailable) |
| GET | `/videos/{video_id}/summary/download` | `summary.txt`, title, completed short/detailed summaries and generation time |

See [AI pipeline documentation](ai-pipeline.md) for the processing and
quality-validation algorithms.
