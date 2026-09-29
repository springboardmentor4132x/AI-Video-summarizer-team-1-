"""Deterministic key moment detection from timestamped transcript segments."""

import math
import re
from dataclasses import dataclass
from typing import Any

from app.models import KeyMoment, Transcript


KEYWORDS = {
    "important", "key", "main", "first", "second", "finally", "conclusion",
    "remember", "recommend", "problem", "solution", "result", "important point",
}
TITLE_KEYWORDS = (
    ("conclusion", "Conclusion"),
    ("recommend", "Recommendation"),
    ("solution", "Solution"),
    ("problem", "Problem"),
    ("result", "Result"),
    ("important point", "Important Point"),
    ("important", "Important Point"),
    ("key", "Key Concept"),
    ("main", "Main Topic"),
)
WORD_PATTERN = re.compile(r"[A-Za-z0-9']+")


class KeyMomentError(ValueError):
    """Raised when a transcript cannot be used for detection."""


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


def _segments(transcript: Transcript) -> list[Segment]:
    if not isinstance(transcript.segments, list) or not transcript.segments:
        raise KeyMomentError("The transcript has no timestamped segments.")

    normalized: list[Segment] = []
    for index, raw in enumerate(transcript.segments):
        if not isinstance(raw, dict):
            raise KeyMomentError(f"Transcript segment {index + 1} is invalid.")
        start_value = raw.get("start_time", raw.get("start"))
        end_value = raw.get("end_time", raw.get("end"))
        text = raw.get("text")
        if not isinstance(start_value, (int, float)) or not isinstance(end_value, (int, float)):
            raise KeyMomentError(f"Transcript segment {index + 1} has invalid timestamps.")
        if not math.isfinite(float(start_value)) or not math.isfinite(float(end_value)) or float(end_value) <= float(start_value):
            raise KeyMomentError(f"Transcript segment {index + 1} has an invalid time range.")
        if not isinstance(text, str) or not text.strip():
            raise KeyMomentError(f"Transcript segment {index + 1} has no text.")
        normalized.append(Segment(float(start_value), float(end_value), text.strip()))
    return normalized


def _word_set(text: str) -> set[str]:
    return {word.lower() for word in WORD_PATTERN.findall(text)}


def _groups(segments: list[Segment]) -> list[list[Segment]]:
    """Split on meaningful lexical shifts rather than fixed time intervals."""
    groups: list[list[Segment]] = [[]]
    boundary_cues = {"now", "next", "finally", "in conclusion", "moving on"}
    for segment in segments:
        current = groups[-1]
        if current:
            previous_words = _word_set(current[-1].text)
            current_words = _word_set(segment.text)
            similarity = len(previous_words & current_words) / max(1, len(previous_words | current_words))
            starts_new_topic = any(segment.text.lower().startswith(cue) for cue in boundary_cues)
            if similarity < 0.15 and len(current) >= 2 or starts_new_topic:
                groups.append([])
        groups[-1].append(segment)
    return [group for group in groups if group]


def _topic(text: str) -> str:
    words = [word for word in WORD_PATTERN.findall(text) if len(word) > 2]
    if not words:
        return "General Discussion"
    return " ".join(words[:4]).title()


def _title(text: str) -> str:
    lowered = text.lower()
    for keyword, title in TITLE_KEYWORDS:
        if keyword in lowered:
            return title
    return "Key Concept"


def _score(group: list[Segment], previous: list[Segment] | None, longest_duration: float, longest_words: int) -> float:
    text = " ".join(segment.text for segment in group)
    words = _word_set(text)
    keyword_hits = sum(1 for keyword in KEYWORDS if keyword in text.lower())
    duration = group[-1].end - group[0].start
    previous_words = _word_set(" ".join(segment.text for segment in previous)) if previous else words
    topic_change = 1 - (len(words & previous_words) / max(1, len(words | previous_words))) if previous else 0
    return (
        0.25 * min(1, duration / max(1, longest_duration))
        + 0.25 * min(1, len(words) / max(1, longest_words))
        + 0.30 * min(1, keyword_hits / 2)
        + 0.20 * topic_change
    )


def detect_key_moments(transcript: Transcript) -> list[KeyMoment]:
    """Build 5-10 transcript-backed moments without calling an AI service."""
    segments = _segments(transcript)
    groups = _groups(segments)
    if not groups:
        raise KeyMomentError("The transcript is empty.")
    longest_duration = max(group[-1].end - group[0].start for group in groups)
    longest_words = max(len(_word_set(" ".join(segment.text for segment in group))) for group in groups)
    scored = [(_score(group, groups[index - 1] if index else None, longest_duration, longest_words), group) for index, group in enumerate(groups)]
    selected_count = min(len(scored), max(1, min(10, math.ceil(len(segments) / 4))))
    selected = sorted(sorted(scored, key=lambda item: item[0], reverse=True)[:selected_count], key=lambda item: item[1][0].start)
    maximum = max(score for score, _ in selected) or 1

    moments: list[KeyMoment] = []
    for score, group in selected:
        text = " ".join(segment.text for segment in group)
        words = text.split()
        description = " ".join(words[:35]) + ("..." if len(words) > 35 else "")
        moments.append(KeyMoment(
            video_id=transcript.video_id,
            start_time=group[0].start,
            end_time=group[-1].end,
            title=_title(text) if _title(text) != "Key Concept" else _topic(text),
            topic=_topic(text),
            description=description,
            importance_score=round(score / maximum, 4),
            transcript_text=text,
        ))
    return moments
