"""Explainable, timestamp-preserving key-moment detection for Module 3."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import os
import re
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.models.key_moment import KeyMoment as KeyMomentModel
from app.services.embedding_service import generate_embeddings
from app.services.keyword_extraction_service import extract_keyphrases

STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "could", "do", "does", "for", "from", "had", "has", "have", "he", "her", "his", "how", "i", "if", "in", "into", "is", "it", "its", "just", "me", "more", "my", "of", "on", "or", "our", "so", "than", "that", "the", "their", "them", "there", "these", "they", "this", "to", "was", "we", "were", "what", "when", "which", "who", "will", "with", "you", "your"}
_CONTINUATION_WORDS = {"so", "but", "and", "because", "since", "when", "while", "though", "however"}
GENERIC_WORDS = STOP_WORDS | {
    # Filler / discourse markers that carry no topic meaning
    "actually", "also", "back", "come", "course", "first", "free", "get", "here",
    "important", "make", "next", "number", "one", "part", "really", "second",
    "thing", "things", "today", "two", "useful", "way", "welcome", "well", "now",
    "lets", "like",
    # Generic conversational / continuation tokens that are NOT acceptable labels
    "any", "before", "behind", "then", "anyway", "anywhere", "basically", "actually",
    "right", "so", "ah", "yeah", "yep", "nope", "hmm", "um", "uh", "er", "okay",
    "ok", "great", "sure", "cool", "kind", "sort", "lot", "maybe", "perhaps",
}


@dataclass
class TranscriptSegment:
    start: float
    end: float
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

@dataclass
class KeyMoment:
    start_time: float
    end_time: float
    title: str
    topic: str | None
    importance_score: float
    text: str


def _value(segment: TranscriptSegment | dict[str, Any], field: str, default: Any = None) -> Any:
    return segment.get(field, default) if isinstance(segment, dict) else getattr(segment, field, default)

def _valid_timestamp(value: Any) -> bool:
    try: return math.isfinite(float(value))
    except (TypeError, ValueError): return False

def tokenize(text: str) -> list[str]:
    return [word for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", text.lower()) if len(word) > 2 and word not in GENERIC_WORDS]

def segment_transcript(segments: list[TranscriptSegment | dict[str, Any]], max_chars: int = 900) -> list[TranscriptChunk]:
    """Validate source segments; Whisper timestamps are never reconstructed."""
    chunks: list[TranscriptChunk] = []
    previous_start = -1.0
    for index, segment in enumerate(segments):
        start, end, text = _value(segment, "start"), _value(segment, "end"), _value(segment, "text", "")
        if not _valid_timestamp(start) or not _valid_timestamp(end) or not isinstance(text, str): continue
        start, end, text = float(start), float(end), text.strip()
        if start < 0 or end <= start or start < previous_start or not text: continue
        if not tokenize(text) and len(text.split()) < 3: continue
        chunks.append(TranscriptChunk(text, start, end, [index]))
        previous_start = start
    return chunks

def cosine_similarity(first: Any, second: Any) -> float:
    left, right = np.asarray(first, dtype=float).ravel(), np.asarray(second, dtype=float).ravel()
    if left.size == 0 or right.size == 0 or left.size != right.size: return 0.0
    denominator = np.linalg.norm(left) * np.linalg.norm(right)
    return float(np.clip(np.dot(left, right) / denominator, -1.0, 1.0)) if denominator else 0.0

def calculate_similarities(embeddings: np.ndarray) -> list[float]:
    return [cosine_similarity(embeddings[i], embeddings[i + 1]) for i in range(max(0, len(embeddings) - 1))]

def extract_keywords(segments: list[TranscriptSegment | dict[str, Any]], max_keywords: int = 10) -> list[str]:
    """Use KeyBERT phrase scores; preserve the old IDF signal as outage fallback."""
    text = " ".join(
        _value(segment, "text", "").strip()
        for segment in segments
        if isinstance(_value(segment, "text", ""), str)
    )
    phrases = extract_keyphrases(text, top_n=max_keywords)
    if phrases:
        return [str(item["phrase"]) for item in phrases]
    documents = [tokenize(_value(s, "text", "")) for s in segments if isinstance(_value(s, "text", ""), str)]
    documents = [doc for doc in documents if doc]
    if not documents: return []
    frequency = Counter(word for doc in documents for word in doc)
    document_frequency = Counter(word for doc in documents for word in set(doc))
    total = len(documents)
    scored = ((word, count * (math.log((total + 1) / (document_frequency[word] + 1)) + 1)) for word, count in frequency.items())
    return [word for word, _ in sorted(scored, key=lambda item: (-item[1], -frequency[item[0]], item[0]))[:max_keywords]]

def _phrase_candidates(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", text.lower())
    return [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1) if len(words[i]) > 2 and len(words[i + 1]) > 2 and words[i] not in GENERIC_WORDS and words[i + 1] not in GENERIC_WORDS]

def _format_label(label: str) -> str:
    """Preserve readable technical acronyms without maintaining a domain list."""
    return " ".join(word.upper() if len(word) <= 3 and word.isalpha() else word.title() for word in label.split())

def _topic_label(text: str, global_keywords: list[str], used_labels: set[str] | None = None) -> str | None:
    words = tokenize(text)
    if not words: return None
    present_phrases = [phrase for phrase in global_keywords if len(phrase.split()) > 1 and all(part in text.casefold() for part in phrase.casefold().split())]
    if present_phrases:
        # Prefer conceptual phrases (noun + noun/adjective) over action phrases (verb + object).
        # Count occurrences and prefer more frequent, multi-word technical terms.
        text_lower = text.casefold()
        phrase_scores = []
        for phrase in present_phrases:
            count = text_lower.count(phrase.casefold())
            # Score based on phrase length (longer = more specific) and frequency
            word_count = len(phrase.split())
            score = (word_count * 2) + count  # Prefer longer phrases first, then by frequency
            phrase_scores.append((phrase, score))
        # Sort by score descending
        for phrase, _ in sorted(phrase_scores, key=lambda x: -x[1]):
            label = _format_label(phrase)
            if not used_labels or label.casefold() not in {item.casefold() for item in used_labels}:
                return label
    global_rank = {word: i for i, word in enumerate(global_keywords)}
    phrases = Counter(_phrase_candidates(text))
    # Prefer repeated phrases, then phrases whose terms are globally salient.
    if phrases:
        phrase, count = sorted(
            phrases.items(),
            key=lambda item: (-item[1], min(global_rank.get(p, len(global_rank)) for p in item[0].split()), item[0]),
        )[0]
        if count >= 2 or all(part in global_rank for part in phrase.split()):
            label = _format_label(phrase)
            if not used_labels or label not in used_labels: return label
    counts = Counter(words)
    # Fallback to a content term. Prefer globally salient terms (TF-IDF) over
    # raw local frequency so generic local words ("bunch", "any", "then")
    # cannot win when stronger transcript-derived candidates exist.
    # A lower index means a more salient corpus term.  Keep that ordering
    # ascending; negating it accidentally promoted unknown local filler.
    ordered = sorted(counts, key=lambda w: (global_rank.get(w, len(global_rank)), -counts[w], w))
    for word in ordered:
        label = _format_label(word)
        if label.lower() not in GENERIC_WORDS:
            if not used_labels or label not in used_labels: return label
    # Last resort: any remaining non-generic local term.
    for word in sorted(counts, key=lambda w: (-(counts[w]), w)):
        label = _format_label(word)
        if label.lower() not in GENERIC_WORDS:
            if not used_labels or label not in used_labels: return label
    return "General Discussion"

def _boundary_cutoff(similarities: list[float], configured_threshold: float) -> float:
    if not similarities: return configured_threshold
    values = np.asarray(similarities, dtype=float)
    # A relative cutoff prevents a generally low-similarity transcript from
    # treating every vocabulary shift as a new subject.
    adaptive = float(np.median(values) - max(0.08, np.std(values) * 0.5))
    return min(configured_threshold, adaptive)

def _is_confirmed_boundary(similarities: list[float], index: int, cutoff: float) -> bool:
    """A single similarity dip is a SIGNAL, not proof of a new topic.

    Accept a boundary only when there is corroborating evidence:
      * a sharp local drop (the dip is far below both neighbours), or
      * a sustained low-similarity pair (two consecutive dips below cutoff).

    This prevents isolated noise from fragmenting an otherwise continuous
    discussion, while still preserving genuinely sharp topic transitions.
    """
    if not (0 <= index < len(similarities)) or similarities[index] >= cutoff:
        return False
    left = similarities[index - 1] if index > 0 else None
    right = similarities[index + 1] if index < len(similarities) - 1 else None
    # Sharp drop: this dip is clearly below its neighbours.
    if left is not None and right is not None:
        if (left - similarities[index]) >= 0.10 and (right - similarities[index]) >= 0.10:
            return True
    # A final transition has no following value to corroborate it. Preserve it
    # only when it is an unusually large separation, rather than treating every
    # trailing dip as a topic change.
    if right is None and left is not None and left - similarities[index] >= .35:
        return True
    # Sustained low similarity: next boundary is also below cutoff.
    if index + 1 < len(similarities) and similarities[index + 1] < cutoff:
        return True
    return False


def _merge_small_regions(regions: list[list[TranscriptChunk]], min_region_chunks: int) -> list[list[TranscriptChunk]]:
    """Defensively merge any region smaller than ``min_region_chunks`` into its
    stronger neighbour. The minimum-region guard only prevents *starting* a
    region too small, not the trailing region ending small; this pass
    guarantees no under-sized region survives regardless of parameters.
    """
    if not regions:
        return regions
    merged = list(regions)
    min_region_chunks = max(1, min_region_chunks)
    changed = True
    while changed:
        changed = False
        for i, group in enumerate(merged):
            if len(group) >= min_region_chunks:
                continue
            prev_group = merged[i - 1] if i > 0 else None
            next_group = merged[i + 1] if i < len(merged) - 1 else None
            if prev_group is None and next_group is None:
                continue
            target = next_group if (prev_group is None or (next_group is not None and len(next_group) >= len(prev_group))) else prev_group
            if target is prev_group:
                merged[i - 1] = prev_group + group
            else:
                merged[i + 1] = group + next_group
            del merged[i]
            changed = True
            break
    return merged


def detect_topics_semantic(chunks: list[TranscriptChunk], embeddings: np.ndarray, similarities: list[float], boundary_threshold: float = 0.45, min_region_chunks: int = 2) -> list[TopicRegion]:
    """Use neighboring embedding continuity and a minimum-region guard."""
    if not chunks: return []
    min_region_chunks = max(1, min_region_chunks)
    cutoff, groups, current = _boundary_cutoff(similarities, boundary_threshold), [], [chunks[0]]
    for index, chunk in enumerate(chunks[1:]):
        # ``index`` addresses a boundary before chunks[index + 1].  A new
        # region is allowed only when it can itself meet the minimum size AND
        # the similarity drop is confirmed (sharp or sustained) rather than a
        # single isolated dip that would fragment continuous discussion.
        remaining = len(chunks) - (index + 1)
        if len(current) >= min_region_chunks and remaining >= min_region_chunks and index < len(similarities) and _is_confirmed_boundary(similarities, index, cutoff):
            groups.append(current); current = [chunk]
        else: current.append(chunk)
    groups.append(current)
    groups = _merge_small_regions(groups, min_region_chunks)
    keywords, used, result = extract_keywords([{"text": c.text} for c in chunks]), set(), []
    for group in groups:
        label = _topic_label(" ".join(c.text for c in group), keywords, used)
        if label: used.add(label)
        result.append(TopicRegion(label, group[0].start_time, group[-1].end_time, group))
    return result

def interval_iou(first: KeyMoment, second: KeyMoment) -> float:
    intersection = max(0.0, min(first.end_time, second.end_time) - max(first.start_time, second.start_time))
    union = max(first.end_time, second.end_time) - min(first.start_time, second.start_time)
    return intersection / union if union else 0.0

def remove_overlaps(candidates: list[KeyMoment], overlap_threshold: float = 0.25) -> list[KeyMoment]:
    selected: list[KeyMoment] = []
    for candidate in sorted(candidates, key=lambda item: (-item.importance_score, item.start_time, item.end_time)):
        def coverage_of_shorter(existing: KeyMoment) -> float:
            overlap = max(0.0, min(candidate.end_time, existing.end_time) - max(candidate.start_time, existing.start_time))
            shorter = min(candidate.end_time - candidate.start_time, existing.end_time - existing.start_time)
            return overlap / shorter if shorter > 0 else 0.0
        if all(coverage_of_shorter(existing) < overlap_threshold for existing in selected): selected.append(candidate)
    return sorted(selected, key=lambda item: item.start_time)

def _build_title(text: str, keywords: list[str]) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", text.strip())[0] if text.strip() else ""
    if len(sentence) > 80: return sentence[:77].rstrip() + "..."
    return sentence or ("Discussion about " + ", ".join(keywords[:3]) if keywords else "Important moment")

def _importance(text: str, topic: TopicRegion, keywords: list[str]) -> float:
    words = tokenize(text)
    if not words: return 0.0
    content_terms = set(words)
    keyword_terms = {token for phrase in keywords for token in tokenize(phrase)}
    keyword_coverage = len(content_terms & keyword_terms) / min(len(content_terms), max(1, len(keyword_terms)))
    richness = min(1.0, len(words) / 28.0)
    topic_words = set(tokenize(" ".join(chunk.text for chunk in topic.chunks)))
    topic_relevance = len(set(words) & topic_words) / len(set(words))
    # 0-1 heuristic relevance: 45% KeyBERT/keyphrase fit, 30% information
    # density and 25% topic fit. Position is handled by topic-diverse selection.
    return round(min(1.0, 0.45 * keyword_coverage + 0.30 * richness + 0.25 * topic_relevance), 3)


# Textual cues that indicate a segment begins mid-sentence and therefore
# needs to be joined with the preceding timestamped chunk for context.
_CONTINATION_WORDS = {"so", "but", "and", "because", "since", "when", "while", "though", "however"}


def _starts_mid_sentence(text: str) -> bool:
    """Heuristic: a chunk is a sentence fragment if it starts lowercase, starts
    with a bare clause word, or starts with punctuation (Whisper often splits
    mid-sentence and leaves the fragment start out of its own timestamp)."""
    if not text:
        return False
    stripped = text.lstrip()
    if not stripped:
        return False
    first = stripped[0]
    if first in ".,;:!?)\"'-)]}>":
        return True
    first_word = re.split(r"[^\w']", stripped)[0].lower()
    if first_word in _CONTINUATION_WORDS:
        return True
    if first != first.upper() and first.isalpha():
        # Lowercase alpha start that is not a continuation word is still a
        # continuation when it lacks terminal punctuation at the prior end.
        return True
    return False


def _ends_complete_sentence(text: str) -> bool:
    """A chunk ends at a sentence boundary if it closes with terminal
    punctuation (optionally quoted)."""
    if not text:
        return False
    stripped = text.rstrip().rstrip(')"\'')
    return bool(stripped) and stripped[-1] in ".!?"


def _expand_to_sentence_boundaries(chunks: list[TranscriptChunk], index: int, max_lookaround: int = 2) -> tuple[int, int, str]:
    """Expand a single-chunk selection to natural sentence boundaries.

    Only the *immediately preceding* chunk within the same region supplies
    context (we never cross topic regions), and expansion is bounded by
    ``max_lookaround`` chunks in each direction.  Timestamps always come from
    the existing Whisper chunks — none are fabricated.

    Returns the (start_index, end_index, joined_text) of the bounded span.
    """
    start = index
    # Backward expansion: a lowercase/clausal start is not independently
    # understandable. Include its immediate predecessor even if that segment
    # happens to carry punctuation; Whisper punctuation is often attached to a
    # split rather than a reliable sentence boundary.
    if _starts_mid_sentence(chunks[index].text):
        steps = 0
        while start > 0 and steps < max_lookaround:
            start -= 1
            steps += 1
            if _ends_complete_sentence(chunks[start].text):
                break
    end = index
    # Forward expansion: extend while the current end is mid-sentence and the
    # next chunk continues the same sentence.
    steps = 0
    while end < len(chunks) - 1 and steps < max_lookaround:
        if _ends_complete_sentence(chunks[end].text):
            break
        successor = chunks[end + 1]
        if _starts_mid_sentence(successor.text):
            end += 1
            steps += 1
        else:
            break
    return start, end, " ".join(c.text.strip() for c in chunks[start:end + 1])


def _expand_candidate(chunks: list[TranscriptChunk], index: int) -> tuple[int, int, str]:
    """Build a 6-35 second contextual window using only source segment times."""
    minimum = max(1.0, float(os.getenv("KEY_MOMENT_MIN_SECONDS", "6")))
    maximum = max(minimum, float(os.getenv("KEY_MOMENT_MAX_SECONDS", "35")))
    start, end, text = _expand_to_sentence_boundaries(chunks, index, max_lookaround=2)
    while chunks[end].end_time - chunks[start].start_time < minimum or len(tokenize(text)) < 4:
        options = []
        if start > 0:
            options.append((start - 1, end))
        if end + 1 < len(chunks):
            options.append((start, end + 1))
        options = [span for span in options if chunks[span[1]].end_time - chunks[span[0]].start_time <= maximum]
        if not options:
            break
        # Prefer the adjacent segment carrying the most new content words.
        def added_content(span):
            included = set(tokenize(" ".join(c.text for c in chunks[start:end + 1])))
            candidate_text = " ".join(c.text for c in chunks[span[0]:span[1] + 1])
            return len(set(tokenize(candidate_text)) - included)
        start, end = max(options, key=added_content)
        text = " ".join(c.text.strip() for c in chunks[start:end + 1])
    return start, end, text


def _select_topic_diverse(candidates: list[KeyMoment], limit: int) -> list[KeyMoment]:
    """Round-robin ranked candidates by topic before filling remaining slots."""
    ranked = sorted(candidates, key=lambda item: (-item.importance_score, item.start_time))
    groups: dict[str, list[KeyMoment]] = {}
    for item in ranked:
        groups.setdefault((item.topic or "General Discussion").casefold(), []).append(item)
    selected: list[KeyMoment] = []
    while len(selected) < limit and groups:
        for topic in list(groups):
            if groups[topic]:
                selected.append(groups[topic].pop(0))
                if len(selected) >= limit:
                    break
            if not groups[topic]:
                del groups[topic]
    return selected

def detect_key_moments(segments: list[TranscriptSegment | dict[str, Any]], threshold: float = 0.30, max_moments: int = 10) -> list[KeyMoment]:
    chunks = segment_transcript(segments)
    if not chunks or max_moments <= 0: return []
    keywords = extract_keywords([{"text": c.text} for c in chunks])
    candidates: list[KeyMoment] = []
    try:
        embeddings = generate_embeddings([c.text for c in chunks])
        # For a very short transcript, a strong semantic discontinuity is enough
        # evidence to allow single-chunk regions; longer videos retain the guard.
        # A longer transcript needs persistent evidence before declaring a new
        # topic.  This is transcript-length based, not a target topic count.
        minimum_evidence = 1 if len(chunks) <= 2 else max(2, math.ceil(math.sqrt(len(chunks)) / 2))
        regions = detect_topics_semantic(chunks, embeddings, calculate_similarities(embeddings), min_region_chunks=minimum_evidence)
    except Exception:
        # Deterministic text fallback only: no fake/mock embeddings are created.
        regions = [TopicRegion(_topic_label(" ".join(c.text for c in chunks), keywords), chunks[0].start_time, chunks[-1].end_time, chunks)]
    for region in regions:
        regional = []
        for index, chunk in enumerate(region.chunks):
            start_index, end_index, text = _expand_candidate(region.chunks, index)
            content_words = tokenize(text)
            if len(content_words) < 4 or len(set(content_words)) < 3:
                continue
            span = region.chunks[start_index:end_index + 1]
            duration = span[-1].end_time - span[0].start_time
            maximum = max(float(os.getenv("KEY_MOMENT_MIN_SECONDS", "6")), float(os.getenv("KEY_MOMENT_MAX_SECONDS", "35")))
            if duration > maximum:
                continue
            regional.append(KeyMoment(span[0].start_time, span[-1].end_time, _build_title(text, keywords), region.label or "General Discussion", _importance(text, region, keywords), text))
        regional = [item for item in regional if item.importance_score >= threshold]
        if regional:
            # For small, continuous regions, limit to 1-2 candidates.
            # Larger regions get up to 3 candidates for diversity.
            # This prevents fragmenting short topics into many near-identical moments.
            max_per_region = 1 if len(region.chunks) <= 2 else (2 if len(region.chunks) <= 4 else 3)
            candidates.extend(sorted(regional, key=lambda item: (-item.importance_score, item.start_time))[:max_per_region])
    expanded = remove_overlaps(candidates, overlap_threshold=0.35)
    ranked = _select_topic_diverse(expanded, max_moments)
    return sorted(ranked, key=lambda item: item.start_time)

def segment_topics(segments: list[TranscriptSegment | dict[str, Any]]) -> list[dict[str, Any]]:
    chunks = segment_transcript(segments)
    keywords = extract_keywords([{"text": c.text} for c in chunks])
    return [{"start": c.start_time, "end": c.end_time, "topic": _topic_label(c.text, keywords), "text": c.text, "keywords": [k for k in keywords if k in tokenize(c.text)]} for c in chunks]

def save_key_moments(db: Session, video_id: int, moments: list[KeyMoment]) -> list[KeyMomentModel]:
    db.query(KeyMomentModel).filter(KeyMomentModel.video_id == video_id).delete(synchronize_session=False)
    saved = [KeyMomentModel(video_id=video_id, start_time=m.start_time, end_time=m.end_time, title=m.title, topic=m.topic, importance_score=m.importance_score, text=m.text) for m in moments]
    db.add_all(saved); db.flush()
    for moment in saved: db.refresh(moment)
    return saved
