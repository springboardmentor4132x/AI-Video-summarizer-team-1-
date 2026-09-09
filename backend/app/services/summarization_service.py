"""Local extractive summarization for completed transcripts."""

from dataclasses import dataclass
import re

from app.models.transcript import Transcript, TranscriptStatus


@dataclass(frozen=True)
class SummaryResult:
    short_summary: str
    detailed_summary: str


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text.strip()) if sentence.strip()]


def summarize_transcript(transcript: Transcript) -> SummaryResult:
    """Create deterministic summaries without an external AI service."""
    if transcript.status != TranscriptStatus.COMPLETED:
        raise ValueError("Only completed transcripts can be summarized")

    text = (transcript.text or "").strip()
    if not text:
        raise ValueError("A completed transcript must contain text")

    sentences = _sentences(text) or [text]
    short_summary = " ".join(sentences[:2])
    detailed_summary = " ".join(sentences[: min(len(sentences), 8)])
    return SummaryResult(
        short_summary=short_summary,
        detailed_summary=detailed_summary,
    )