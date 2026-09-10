"""Local deterministic summarization for the current demo."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SummaryResult:
    short_summary: str
    detailed_summary: str


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text.strip()) if sentence.strip()]


def summarize_text(text: str) -> SummaryResult:
    """Create a useful local summary without an external paid provider."""
    normalized = " ".join(text.split())
    if not normalized:
        raise ValueError("Cannot summarize empty transcript text")

    sentences = _sentences(normalized)
    short = " ".join(sentences[:2]) or normalized[:240]
    if len(short) > 300:
        short = short[:297].rstrip() + "..."

    detail_sentences = sentences[:8] or [normalized]
    detailed = " ".join(detail_sentences)
    return SummaryResult(short_summary=short, detailed_summary=detailed)
