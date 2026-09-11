from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.models.key_moment import KeyMoment as KeyMomentModel
from app.services.embedding_service import generate_embeddings


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

GENERIC_TOPIC_WORDS = STOP_WORDS | {
    "actually",
    "also",
    "back",
    "come",
    "covers",
    "course",
    "first",
    "free",
    "get",
    "here",
    "important",
    "just",
    "make",
    "more",
    "next",
    "number",
    "one",
    "part",
    "really",
    "second",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "snapshot",
    "sure",
    "that",
    "thing",
    "things",
    "this",
    "two",
    "useful",
    "way",
    "welcome",
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


@dataclass
class TranscriptChunk:
    text: str
    start_time: float
    end_time: float
    source_segment_indexes: list[int]


@dataclass
class TopicRegion:
    label: str | None
    start_time: float
    end_time: float
    chunks: list[TranscriptChunk]


def _valid_timestamp(value: Any) -> bool:
    try:
        return np.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def segment_transcript(segments: list[TranscriptSegment | dict[str, Any]], max_chars: int = 900) -> list[TranscriptChunk]:
    """Group ordered transcript segments without splitting sentence text."""
    chunks: list[TranscriptChunk] = []
    current_text: list[str] = []
    current_indexes: list[int] = []
    current_start: float | None = None
    current_end: float | None = None

    def flush() -> None:
        nonlocal current_text, current_indexes, current_start, current_end
        if current_text and current_start is not None and current_end is not None:
            chunks.append(TranscriptChunk(" ".join(current_text), current_start, current_end, current_indexes))
        current_text, current_indexes = [], []
        current_start, current_end = None, None

    for index, segment in enumerate(segments):
        start = _get_segment_value(segment, "start")
        end = _get_segment_value(segment, "end")
        text = _get_segment_value(segment, "text", "")
        if not _valid_timestamp(start) or not _valid_timestamp(end) or float(end) <= float(start):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        text = text.strip()
        if current_text:
            flush()
        if current_start is None:
            current_start = float(start)
        current_end = float(end)
        current_text.append(text)
        current_indexes.append(index)
    flush()
    return chunks


def cosine_similarity(first: Any, second: Any) -> float:
    """Return cosine similarity safely for empty, zero, or mismatched vectors."""
    left, right = np.asarray(first, dtype=float).ravel(), np.asarray(second, dtype=float).ravel()
    if left.size == 0 or right.size == 0 or left.size != right.size:
        return 0.0
    left_norm, right_norm = np.linalg.norm(left), np.linalg.norm(right)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(np.clip(np.dot(left, right) / (left_norm * right_norm), -1.0, 1.0))


def calculate_similarities(embeddings: np.ndarray) -> list[float]:
    return [cosine_similarity(embeddings[index], embeddings[index + 1]) for index in range(max(0, len(embeddings) - 1))]


def _topic_label(text: str, keywords: list[str]) -> str | None:
    words = [word for word in tokenize(text) if word not in GENERIC_TOPIC_WORDS]
    if not words:
        return None
    local_counts = Counter(words)
    local_keywords = [word for word, _count in local_counts.most_common() if word in keywords]
    return (local_keywords[0] if local_keywords else local_counts.most_common(1)[0][0]).title()


def detect_topics_semantic(
    chunks: list[TranscriptChunk],
    embeddings: np.ndarray,
    similarities: list[float],
    boundary_threshold: float = 0.45,
    min_region_chunks: int = 2,
) -> list[TopicRegion]:
    """Use semantic drops while preventing isolated short topic regions."""
    if not chunks:
        return []
    min_region_chunks = max(1, min_region_chunks)
    keywords = extract_keywords([{"text": chunk.text} for chunk in chunks])
    regions: list[TopicRegion] = []
    current = [chunks[0]]
    for index, chunk in enumerate(chunks[1:]):
        if (
            len(current) >= min_region_chunks
            and index < len(similarities)
            and similarities[index] < boundary_threshold
        ):
            regions.append(TopicRegion(_topic_label(" ".join(item.text for item in current), keywords), current[0].start_time, current[-1].end_time, current))
            current = [chunk]
        else:
            current.append(chunk)
    regions.append(TopicRegion(_topic_label(" ".join(item.text for item in current), keywords), current[0].start_time, current[-1].end_time, current))
    while len(regions) > 1:
        small_index = next((index for index, region in enumerate(regions) if len(region.chunks) < min_region_chunks), None)
        if small_index is None:
            break
        if small_index == 0:
            merge_index = 1
        elif small_index == len(regions) - 1:
            merge_index = small_index - 1
        else:
            merge_index = small_index - 1 if len(regions[small_index - 1].chunks) >= len(regions[small_index + 1].chunks) else small_index + 1
        left_index, right_index = sorted((small_index, merge_index))
        merged_chunks = regions[left_index].chunks + regions[right_index].chunks
        merged_text = " ".join(item.text for item in merged_chunks)
        merged = TopicRegion(_topic_label(merged_text, keywords), merged_chunks[0].start_time, merged_chunks[-1].end_time, merged_chunks)
        regions[left_index:right_index + 1] = [merged]
    return regions


def interval_iou(first: KeyMoment, second: KeyMoment) -> float:
    intersection = max(0.0, min(first.end_time, second.end_time) - max(first.start_time, second.start_time))
    union = max(first.end_time, second.end_time) - min(first.start_time, second.start_time)
    return intersection / union if union > 0 else 0.0


def remove_overlaps(candidates: list[KeyMoment], overlap_threshold: float = 0.25) -> list[KeyMoment]:
    """Keep the stronger candidate when overlap covers the shorter clip.

    The default 0.25 ratio means at least a quarter of the shorter candidate must
    be redundant; this is more useful for highlights of different lengths
    than global IoU alone.
    """
    selected: list[KeyMoment] = []
    for candidate in sorted(candidates, key=lambda item: item.importance_score, reverse=True):
        def overlap_ratio(existing: KeyMoment) -> float:
            intersection = max(0.0, min(candidate.end_time, existing.end_time) - max(candidate.start_time, existing.start_time))
            shorter = min(candidate.end_time - candidate.start_time, existing.end_time - existing.start_time)
            return intersection / shorter if shorter > 0 else 0.0

        if all(overlap_ratio(existing) < overlap_threshold for existing in selected):
            selected.append(candidate)
    return sorted(selected, key=lambda item: item.start_time)


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
):
    """Detect important chunks using local semantic embeddings when available.

    Importance combines keyword density (40%), content density (30%), and
    semantic topic relevance (30%). The keyword fallback keeps existing
    uploads usable when model weights are unavailable, while installed
    Sentence Transformers remains the primary path.
    """
    chunks = segment_transcript(segments)
    if not chunks:
        return []
    keywords = extract_keywords([{"text": chunk.text} for chunk in chunks])
    try:
        embeddings = generate_embeddings([chunk.text for chunk in chunks])
        similarities = calculate_similarities(embeddings)
        regions = detect_topics_semantic(
            chunks,
            embeddings,
            similarities,
            min_region_chunks=1,
        )
    except Exception:
        embeddings = np.empty((0, 0))
        regions = []

    candidates: list[KeyMoment] = []
    for index, chunk in enumerate(chunks):
        keyword_score = _calculate_importance(chunk.text, keywords)
        words = tokenize(chunk.text)
        content_score = min(1.0, len(words) / 35.0)
        semantic_score = 0.0
        topic = _build_topic(chunk.text, keywords)
        if regions:
            region = next((item for item in regions if chunk in item.chunks), None)
            if region:
                topic = region.label
                semantic_score = 1.0 / len(region.chunks)
        score = round(min(1.0, 0.4 * keyword_score + 0.3 * content_score + 0.3 * semantic_score), 2)
        if score < threshold and not regions:
            score = keyword_score
        if score < threshold:
            continue
        candidates.append(KeyMoment(chunk.start_time, chunk.end_time, _build_title(chunk.text, keywords), topic, score, chunk.text))

    return remove_overlaps(
        sorted(candidates, key=lambda item: item.importance_score, reverse=True)
    )[:max_moments]


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
