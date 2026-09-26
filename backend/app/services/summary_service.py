"""Compatibility entry point for local BART summarization.

All callers share the token-safe hierarchical implementation in
``summarization_service``; this module deliberately contains no extractive
first-sentence fallback.
"""

from app.services.summarization_service import summarize_text


def generate_summary_from_transcript(transcript_text: str) -> str:
    """Return the abstractive short summary for actual transcript content."""
    if not transcript_text or not transcript_text.strip():
        raise ValueError("Transcript content is required for summarization")
    return summarize_text(transcript_text).short_summary
