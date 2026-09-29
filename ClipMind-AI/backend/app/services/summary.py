"""AI summary generation service."""

import logging
import re
from dataclasses import dataclass
from collections import Counter

from google import genai
from google.genai import types

from app.config import settings
from app.schemas.summary import GeminiSummaryOutput
from app.services.gemini import (
    GEMINI_REQUEST_TIMEOUT_SECONDS,
    GeminiProviderUnavailableError,
    generate_content_with_retry,
    gemini_http_options,
)

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "how",
    "i", "if", "in", "is", "it", "its", "of", "on", "or", "that", "the", "their", "this", "to",
    "was", "we", "were", "what", "when", "where", "which", "who", "will", "with", "you", "your",
    "so", "then", "they", "there", "about", "can", "do", "just", "like", "more", "not", "our", "than",
}
SIGNAL_WORDS = {
    "important", "key", "main", "conclusion", "finally", "remember", "recommendation", "recommend",
    "problem", "solution", "result", "because", "therefore", "example", "learn", "benefit", "first",
    "second", "next", "summary", "inspiration", "strategy", "lesson",
}
WORD_PATTERN = re.compile(r"[A-Za-z0-9']+")
FILLER_SENTENCES = {
    "hello", "hi", "good morning", "good afternoon", "good evening", "thank you", "thanks", "bye",
    "thanks for watching", "you", "okay", "ok", "right",
}


class SummaryError(Exception):
    """Raised when summary generation cannot be completed."""


def summarize_transcript_with_gemini(transcript_text: str) -> GeminiSummaryOutput:
    """Generate structured summary content only from the selected video's transcript."""
    if not transcript_text or not transcript_text.strip():
        raise SummaryError("Transcript is empty. Generate the transcript first.")

    api_key = (settings.gemini_api_key or "").strip()
    if not api_key:
        raise SummaryError("Gemini API key is not configured.")

    model_name = (settings.gemini_model or "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    try:
        client = genai.Client(
            api_key=api_key,
            http_options=gemini_http_options(GEMINI_REQUEST_TIMEOUT_SECONDS),
        )
        prompt = f"""You are summarizing one selected video's transcript for ClipMind AI.

Use only the transcript provided below. Do not use outside knowledge, invent facts, add unsupported names, statistics, dates, examples, or conclusions, assume missing information, or mix in another video. Preserve the meaning of the speaker's statements. Preserve numerical information only when it is genuinely present and important in this transcript; do not invent or alter numerical facts. If the transcript is insufficient, state that in the summaries rather than filling gaps.

Return a concise short_summary, a detailed long_summary covering the transcript's important ideas, concepts, processes, explanations, and conclusions, and key_points containing meaningful points grounded in the transcript. Return only the requested structured JSON.

SELECTED VIDEO TRANSCRIPT:
<transcript>
{transcript_text}
</transcript>"""
        response = generate_content_with_retry(
            lambda: client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=3000,
                    response_mime_type="application/json",
                    response_schema=GeminiSummaryOutput,
                ),
            ),
            operation="summary",
            model=model_name,
            request_timeout_seconds=GEMINI_REQUEST_TIMEOUT_SECONDS,
        )
        if not getattr(response, "text", None):
            raise SummaryError("Gemini returned no summary content.")
        return GeminiSummaryOutput.model_validate_json(response.text)
    except SummaryError:
        raise
    except GeminiProviderUnavailableError as exc:
        logger.warning(
            "Gemini request failed operation=summary model=%s status_code=%s "
            "exception_type=%s attempts=%s retry=false final_reason=%s",
            model_name,
            exc.status_code,
            type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__,
            exc.attempts,
            exc.reason,
        )
        raise SummaryError(str(exc)) from exc
    except Exception as exc:
        logger.warning(
            "Gemini request failed operation=summary model=%s status_code=%s "
            "provider_status=%s exception_type=%s retry=false final_reason=non_retryable_failure",
            model_name,
            getattr(exc, "code", getattr(exc, "status_code", None)),
            getattr(exc, "status", None),
            type(exc).__name__,
        )
        raise SummaryError("Gemini summary generation failed. Please try again.") from exc


@dataclass(frozen=True)
class StructuredSummary:
    overview: str
    main_points: list[str]
    key_takeaways: list[str]


def _clean_sentences(text: str) -> list[str]:
    """Remove filler and repeated transcript sentences before scoring."""
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
    cleaned: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        normalized = re.sub(r"[^a-z0-9\s]", "", sentence.lower()).strip()
        if normalized in FILLER_SENTENCES or len(WORD_PATTERN.findall(sentence)) < 4 or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(sentence)
    return cleaned


def summarize_transcript(transcript_text: str) -> StructuredSummary:
    """Create a transcript-wide deterministic extractive summary."""
    cleaned = (transcript_text or "").strip()
    if not cleaned:
        raise SummaryError("Transcript is empty. Generate the transcript first.")

    sentences = _clean_sentences(cleaned)
    if not sentences:
        fallback = cleaned.split()
        if len(fallback) < 4:
            raise SummaryError("Transcript does not contain usable text.")
        sentences = [cleaned]

    if len(sentences) == 1:
        return StructuredSummary(sentences[0], sentences, sentences)

    token_sets = []
    frequency = Counter()
    for sentence in sentences:
        tokens = {token.lower() for token in WORD_PATTERN.findall(sentence) if token.lower() not in STOPWORDS and len(token) > 2}
        token_sets.append(tokens)
        frequency.update(tokens)

    section_count = min(4, len(sentences))
    section_size = max(1, (len(sentences) + section_count - 1) // section_count)
    scored: list[tuple[float, int, str]] = []
    for index, (sentence, tokens) in enumerate(zip(sentences, token_sets)):
        if not tokens:
            continue
        position = index / max(1, len(sentences) - 1)
        term_score = sum(min(3, frequency[token]) for token in tokens) / max(1, len(tokens) * 3)
        signal_score = sum(1 for token in tokens if token in SIGNAL_WORDS) / max(1, min(3, len(tokens)))
        length_score = min(1, len(tokens) / 14)
        boundary_score = 0.15 if index == 0 or index == len(sentences) - 1 else 0
        score = (0.38 * term_score) + (0.30 * signal_score) + (0.17 * length_score) + boundary_score
        scored.append((score, index, sentence))

    def select_per_section(limit: int) -> list[tuple[float, int, str]]:
        selected: list[tuple[float, int, str]] = []
        for section in range(section_count):
            start = section * section_size
            end = min(len(sentences), start + section_size)
            candidates = [item for item in scored if start <= item[1] < end]
            selected.extend(sorted(candidates, reverse=True)[:limit])
        return selected

    target_points = min(7, max(3, round(len(sentences) ** 0.5) + 1))
    candidates = select_per_section(2)
    chosen: list[tuple[float, int, str]] = []
    chosen_tokens: list[set[str]] = []
    for candidate in sorted(candidates, reverse=True):
        candidate_tokens = token_sets[candidate[1]]
        if any(len(candidate_tokens & existing) / max(1, len(candidate_tokens | existing)) > 0.72 for existing in chosen_tokens):
            continue
        chosen.append(candidate)
        chosen_tokens.append(candidate_tokens)
        if len(chosen) >= target_points:
            break
    chosen.sort(key=lambda item: item[1])
    main_points = [sentence for _, _, sentence in chosen]
    if not main_points:
        main_points = [sentences[0]]

    overview_sentences = main_points[:min(2, len(main_points))]
    overview = " ".join(overview_sentences)
    conclusion_candidates = [item for item in chosen if item[1] >= len(sentences) * 0.65 or any(word in item[2].lower() for word in ("conclusion", "finally", "in summary", "therefore"))]
    key_takeaways = [sentence for _, _, sentence in (conclusion_candidates or chosen[-min(3, len(chosen)):])]
    return StructuredSummary(overview, main_points, key_takeaways)
