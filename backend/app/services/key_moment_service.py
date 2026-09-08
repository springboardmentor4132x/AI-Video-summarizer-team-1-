from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.key_moment import KeyMoment as KeyMomentModel


# Common words that are not useful as topics/keywords
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "me",
    "more",
    "my",
    "of",
    "on",
    "or",
    "our",
    "so",
    "than",
    "that",
    "the",
    "their",
    "them",
    "there",
    "these",
    "they",
    "this",
    "to",
    "was",
    "we",
    "were",
    "what",
    "when",
    "which",
    "who",
    "will",
    "with",
    "you",
    "your",
}


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class KeyMoment:
    start_time: float
    end_time: float
    title: str
    topic: str | None
    importance_score: float
    text: str


def _get_segment_value(
    segment: TranscriptSegment | dict[str, Any],
    field: str,
    default: Any = None,
) -> Any:
    """
    Get a value from either a TranscriptSegment object or a dictionary.
    """
    if isinstance(segment, dict):
        return segment.get(field, default)

    return getattr(segment, field, default)


def tokenize(text: str) -> list[str]:
    """
    Convert text into lowercase content words.
    """
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", text.lower())

    return [
        word
        for word in words
        if word not in STOP_WORDS and len(word) > 2
    ]


def extract_keywords(
    segments: list[TranscriptSegment | dict[str, Any]],
    max_keywords: int = 10,
) -> list[str]:
    """
    Extract content-bearing keywords using frequency with stop-word removal.

    Supports both TranscriptSegment objects and dictionaries.
    """

    frequencies: Counter[str] = Counter()

    for segment in segments:
        text = _get_segment_value(segment, "text", "")

        if not isinstance(text, str):
            continue

        frequencies.update(tokenize(text))

    return [
        word
        for word, _count in frequencies.most_common(max_keywords)
    ]


def _calculate_importance(
    text: str,
    keywords: list[str],
) -> float:
    """
    Calculate a simple importance score based on keyword density.

    This is intentionally lightweight so Module 3 can work without
    requiring a large ML model at this stage.
    """

    words = tokenize(text)

    if not words:
        return 0.0

    keyword_set = set(keyword.lower() for keyword in keywords)

    keyword_count = sum(
        1 for word in words if word in keyword_set
    )

    density_score = keyword_count / len(words)

    # Keep score between 0 and 1.
    score = min(1.0, density_score * 3.0)

    return round(score, 2)


def _build_title(
    text: str,
    keywords: list[str],
) -> str:
    """
    Generate a simple readable title for a key moment.
    """

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    if sentences and sentences[0]:
        title = sentences[0].strip()

        if len(title) > 80:
            title = title[:77].rstrip() + "..."

        return title

    if keywords:
        return "Discussion about " + ", ".join(keywords[:3])

    return "Important Moment"


def _build_topic(
    text: str,
    keywords: list[str],
) -> str | None:
    """
    Determine a meaningful topic for a transcript segment.

    Prefer multi-word phrases and meaningful content words over
    generic words such as "number", "make", or "one".
    """

    if not isinstance(text, str) or not text.strip():
        return None

    # Words that are technically content words but are poor topics.
    topic_stop_words = {
        "number",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "make",
        "makes",
        "made",
        "get",
        "gets",
        "getting",
        "thing",
        "things",
        "way",
        "ways",
        "part",
        "important",
        "useful",
        "really",
        "actually",
        "also",
        "first",
        "second",
        "third",
        "next",
    }

    words = tokenize(text)

    if not words:
        return None

    # Look for meaningful keywords that occur in this segment.
    matching_keywords = [
        keyword
        for keyword in keywords
        if keyword.lower() in words
        and keyword.lower() not in topic_stop_words
    ]

    if matching_keywords:
        word_counts = Counter(words)

        strongest = max(
            matching_keywords,
            key=lambda keyword: word_counts[keyword.lower()],
        )

        return strongest.title()

    # Fallback: choose the most frequent meaningful word.
    candidates = [
        word
        for word in words
        if word not in topic_stop_words
    ]

    if not candidates:
        return None

    return Counter(candidates).most_common(1)[0][0].title()

def segment_topics(
    segments: list[TranscriptSegment | dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Group consecutive transcript segments into topic-based sections.

    A new topic section is created when the dominant topic changes.
    """

    if not segments:
        return []

    keywords = extract_keywords(segments)

    topic_segments: list[dict[str, Any]] = []

    current_topic = None
    current_start = None
    current_end = None
    current_text: list[str] = []

    for segment in segments:
        start = _get_segment_value(segment, "start")
        end = _get_segment_value(segment, "end")
        text = _get_segment_value(segment, "text", "")

        if start is None or end is None:
            continue

        if not isinstance(text, str) or not text.strip():
            continue

        topic = _build_topic(text, keywords)

        if current_topic is None:
            current_topic = topic
            current_start = float(start)
            current_end = float(end)
            current_text = [text.strip()]
            continue

        if topic == current_topic:
            current_end = float(end)
            current_text.append(text.strip())
        else:
            topic_segments.append(
                {
                    "start": current_start,
                    "end": current_end,
                    "topic": current_topic,
                    "text": " ".join(current_text),
                }
            )

            current_topic = topic
            current_start = float(start)
            current_end = float(end)
            current_text = [text.strip()]

    if current_topic is not None and current_start is not None:
        topic_segments.append(
            {
                "start": current_start,
                "end": current_end,
                "topic": current_topic,
                "text": " ".join(current_text),
            }
        )

    return topic_segments

def detect_key_moments(
    segments: list[TranscriptSegment | dict[str, Any]],
    threshold: float = 0.30,
    max_moments: int = 10,
) -> list[KeyMoment]:
    """
    Detect important transcript segments.

    Current implementation uses keyword frequency and keyword density.
    It does not require an external ML model.

    Later, this function can be replaced or enhanced with an NLP/LLM
    model without changing the API layer.
    """

    if not segments:
        return []

    keywords = extract_keywords(segments)

    candidates: list[KeyMoment] = []

    for segment in segments:
        start = _get_segment_value(segment, "start")
        end = _get_segment_value(segment, "end")
        text = _get_segment_value(segment, "text", "")

        if start is None or end is None:
            continue

        if not isinstance(text, str) or not text.strip():
            continue

        importance_score = _calculate_importance(
            text,
            keywords,
        )

        title = _build_title(
            text,
            keywords,
        )

        topic = _build_topic(
            text,
            keywords,
        )

        candidates.append(
            KeyMoment(
                start_time=float(start),
                end_time=float(end),
                title=title,
                topic=topic,
                importance_score=importance_score,
                text=text.strip(),
            )
        )

    # Sort most important moments first.
    candidates.sort(
        key=lambda moment: moment.importance_score,
        reverse=True,
    )

    selected = candidates[:max_moments]

    # Return them in video order for the frontend.
    selected.sort(
        key=lambda moment: moment.start_time
    )

    return selected


def save_key_moments(
    db: Session,
    video_id: int,
    moments: list[KeyMoment],
) -> list[KeyMomentModel]:
    """
    Save detected key moments for a video.

    Existing key moments for the video are removed before saving
    the newly detected moments.
    """

    db.query(KeyMomentModel).filter(
        KeyMomentModel.video_id == video_id
    ).delete(synchronize_session=False)

    saved_moments: list[KeyMomentModel] = []

    for moment in moments:
        db_moment = KeyMomentModel(
            video_id=video_id,
            start_time=moment.start_time,
            end_time=moment.end_time,
            title=moment.title,
            topic=moment.topic,
            importance_score=moment.importance_score,
            text=moment.text,
        )

        db.add(db_moment)
        saved_moments.append(db_moment)

    db.flush()

    for moment in saved_moments:
        db.refresh(moment)

    return saved_moments
