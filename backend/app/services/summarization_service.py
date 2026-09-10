"""Summaries for completed transcripts.

This service prefers a local Hugging Face model when available, but it falls
back to a deterministic extractive summary so the backend remains reliable in
offline or restricted environments.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any

from app.models.transcript import Transcript, TranscriptStatus


@dataclass(frozen=True)
class SummaryResult:
    short_summary: str
    detailed_summary: str


def _sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text.strip())
        if sentence.strip()
    ]


def _chunk_text(text: str, max_chars: int = 1800) -> list[str]:
    paragraphs = re.split(r"\n+|(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for paragraph in paragraphs:
        stripped = paragraph.strip()
        if not stripped:
            continue
        if current_length + len(stripped) > max_chars and current:
            chunks.append(" ".join(current))
            current = [stripped]
            current_length = len(stripped)
        else:
            current.append(stripped)
            current_length += len(stripped)

    if current:
        chunks.append(" ".join(current))

    return chunks or [text.strip()]


def _heuristic_summary(text: str) -> SummaryResult:
    sentences = _sentences(text) or [text]
    short_summary = " ".join(sentences[:2])
    detailed_summary = " ".join(sentences[: min(len(sentences), 8)])
    return SummaryResult(
        short_summary=short_summary,
        detailed_summary=detailed_summary,
    )


def _summarize_with_hf(text: str) -> SummaryResult | None:
    """Attempt a local Hugging Face summarization pipeline when available."""
    try:
        from transformers import pipeline
    except Exception:
        return None

    model_name = os.getenv("LOCAL_SUMMARY_MODEL", "facebook/bart-large-cnn").strip() or "facebook/bart-large-cnn"

    try:
        summarizer = pipeline("summarization", model=model_name, tokenizer=model_name, device=-1)
    except Exception:
        return None

    try:
        chunks = _chunk_text(text)
        if len(chunks) == 1:
            result = summarizer(
                chunks[0],
                max_length=120,
                min_length=20,
                do_sample=False,
            )
            summary_text = result[0]["summary_text"].strip() if result else chunks[0]
            return SummaryResult(
                short_summary=summary_text,
                detailed_summary=summary_text,
            )

        chunk_outputs: list[str] = []
        for chunk in chunks:
            result = summarizer(
                chunk,
                max_length=min(120, max(40, len(chunk.split()) // 2)),
                min_length=15,
                do_sample=False,
            )
            if result:
                chunk_outputs.append(result[0]["summary_text"].strip())

        combined = " ".join(part for part in chunk_outputs if part).strip()
        if not combined:
            return _heuristic_summary(text)

        short_summary = combined if len(combined) <= 240 else combined[:237].rstrip() + "..."
        detailed_summary = combined if len(combined) <= 900 else combined[:897].rstrip() + "..."
        return SummaryResult(short_summary=short_summary, detailed_summary=detailed_summary)
    except Exception:
        return None


def summarize_transcript(transcript: Transcript) -> SummaryResult:
    """Create a clean summary while keeping offline execution safe."""
    if transcript.status != TranscriptStatus.COMPLETED:
        raise ValueError("Only completed transcripts can be summarized")

    text = (transcript.text or "").strip()
    if not text:
        raise ValueError("A completed transcript must contain text")

    hf_result = _summarize_with_hf(text)
    if hf_result is not None:
        return hf_result

    return _heuristic_summary(text)
