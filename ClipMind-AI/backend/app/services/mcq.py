"""Generate grounded MCQ questions from the video's transcript, summary, and key moments."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from google import genai

from app.config import settings
from app.models import Video
from app.services.gemini import (
    GEMINI_SHORT_REQUEST_TIMEOUT_SECONDS,
    GeminiProviderUnavailableError,
    generate_content_with_retry,
    gemini_http_options,
)

logger = logging.getLogger(__name__)


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _format_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        total_seconds = max(0, int(float(value)))
    except (TypeError, ValueError):
        return None
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _candidate_texts(video: Video) -> dict[str, list[str]]:
    transcript_texts: list[str] = []
    if video.transcript:
        transcript_texts.append(video.transcript.text or "")
        if video.transcript.segments:
            for segment in video.transcript.segments:
                if isinstance(segment, dict):
                    segment_text = _normalize_text(str(segment.get("text", "")))
                    if segment_text:
                        transcript_texts.append(segment_text)

    summary_texts: list[str] = []
    if video.summary:
        summary_texts.extend([video.summary.overview, *video.summary.main_points, *video.summary.key_takeaways])

    key_moment_texts: list[str] = []
    for moment in video.key_moments or []:
        key_moment_texts.extend([moment.topic or "", moment.title, moment.description])

    return {
        "transcript": transcript_texts,
        "summary": summary_texts,
        "key_moment": key_moment_texts,
    }


def _tokenize_for_grounding(value: str) -> list[str]:
    text = _normalize_text(value).lower()
    if not text:
        return []
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens: list[str] = []
    for token in text.split():
        if not token:
            continue
        if token in {"a", "an", "the", "to", "of", "in", "on", "for", "with", "it", "is", "are", "was", "were", "and", "or", "but", "if", "then", "that", "this", "these", "those", "from", "by", "as", "at", "be", "its", "their", "there", "into", "about", "through", "using", "used", "does", "do", "did", "has", "have", "had", "not"}:
            continue
        if token.endswith("ies") and len(token) > 3:
            token = token[:-3] + "y"
        elif token.endswith("sses") and len(token) > 4:
            token = token[:-2]
        elif token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
            token = token[:-1]
        tokens.append(token)
    return tokens


def _answer_matches_context(answer: str, context: str) -> bool:
    answer_text = _normalize_text(answer)
    context_text = _normalize_text(context)
    if not answer_text or not context_text:
        return False

    answer_lower = answer_text.lower()
    context_lower = context_text.lower()
    if answer_lower in context_lower or context_lower in answer_lower:
        return True

    answer_tokens = _tokenize_for_grounding(answer_text)
    context_tokens = _tokenize_for_grounding(context_text)
    if not answer_tokens or not context_tokens:
        return False

    answer_token_set = set(answer_tokens)
    context_token_set = set(context_tokens)
    overlap = answer_token_set & context_token_set
    if not overlap:
        return False

    overlap_count = len(overlap)
    if len(answer_token_set) <= 4:
        return overlap_count >= 2
    if len(answer_token_set) <= 8:
        return overlap_count >= 3
    return overlap_count >= 4 and (overlap_count / len(answer_token_set)) >= 0.35


def _source_supports_answer(video: Video, source: str, answer: str) -> bool:
    answer_text = _normalize_text(answer)
    if not answer_text:
        return False

    evidence = _candidate_texts(video)
    if source == "Transcript":
        contexts = evidence["transcript"]
    elif source == "Summary":
        contexts = evidence["summary"]
    elif source == "Key Moment":
        contexts = evidence["key_moment"]
    else:
        contexts = []

    return any(_answer_matches_context(answer_text, value) for value in contexts)


def _extract_json_array(raw_text: str) -> list[dict[str, Any]]:
    if not raw_text:
        raise ValueError("Gemini returned an empty response.")

    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    parsed = json.loads(cleaned)
    if isinstance(parsed, dict):
        for key in ("mcqs", "questions", "items"):
            candidate = parsed.get(key)
            if isinstance(candidate, list):
                parsed = candidate
                break
        else:
            raise ValueError("Gemini response was not a list of MCQs.")

    if not isinstance(parsed, list):
        raise ValueError("Gemini response was not a JSON array.")

    return parsed


def _validate_and_normalize_mcq(item: Any, video: Video) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    question = _normalize_text(str(item.get("question", "")))
    if not question:
        return None

    options = item.get("options")
    if not isinstance(options, list):
        return None

    cleaned_options: list[str] = []
    seen: set[str] = set()
    for option in options:
        option_text = _normalize_text(str(option))
        if not option_text:
            continue
        key = option_text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_options.append(option_text)

    if len(cleaned_options) != 4:
        return None

    correct_answer = _normalize_text(str(item.get("correct_answer", "")))
    if not correct_answer or correct_answer not in cleaned_options:
        return None

    explanation = _normalize_text(str(item.get("explanation", "")))
    if not explanation:
        return None

    difficulty = str(item.get("difficulty", "")).strip()
    if difficulty not in {"Easy", "Medium", "Hard"}:
        return None

    source = str(item.get("source", "")).strip()
    if source not in {"Transcript", "Summary", "Key Moment"}:
        return None

    topic = _normalize_text(str(item.get("topic", "")))
    if not topic:
        return None

    raw_timestamp = item.get("timestamp")
    if raw_timestamp is None or str(raw_timestamp).strip() in {"", "null", "None"}:
        timestamp: str | None = None
    else:
        timestamp = _normalize_text(str(raw_timestamp))
        if not re.fullmatch(r"\d{1,2}:\d{2}", timestamp):
            try:
                float_value = float(timestamp)
            except ValueError:
                return None
            timestamp = _format_timestamp(float_value)

    if source == "Summary":
        timestamp = None

    if source in {"Transcript", "Key Moment"} and timestamp is not None and not re.fullmatch(r"\d{1,2}:\d{2}", timestamp):
        return None

    if not _source_supports_answer(video, source, correct_answer):
        return None

    normalised_question = question.lower()
    if question.lower() == correct_answer.lower():
        return None

    if any(_normalize_text(str(option)).lower() == normalised_question for option in cleaned_options):
        return None

    if len(question) < 12 or "according to the transcript" in question.lower() and len(question) < 30:
        return None

    return {
        "question": question,
        "options": cleaned_options,
        "correct_answer": correct_answer,
        "explanation": explanation,
        "difficulty": difficulty,
        "topic": topic,
        "source": source,
        "timestamp": timestamp,
    }


def _get_gemini_client() -> genai.Client:
    api_key = (settings.gemini_api_key or "").strip()
    if not api_key:
        raise ValueError("Gemini API key is not configured.")
    return genai.Client(
        api_key=api_key,
        http_options=gemini_http_options(GEMINI_SHORT_REQUEST_TIMEOUT_SECONDS),
    )


def _build_gemini_prompt(video: Video) -> str:
    transcript = video.transcript
    summary = video.summary
    key_moments = video.key_moments or []

    def format_text_block(title: str, values: list[str]) -> str:
        filtered = [_normalize_text(value) for value in values]
        cleaned = [value for value in filtered if value]
        if not cleaned:
            return f"{title}\n- No data available\n"
        return f"{title}\n" + "\n".join(f"- {value}" for value in cleaned) + "\n"

    transcript_block = "TRANSCRIPT\n- No transcript available\n"
    if transcript:
        transcript_segments = []
        if transcript.segments:
            for segment in transcript.segments:
                if not isinstance(segment, dict):
                    continue
                text = _normalize_text(str(segment.get("text", "")))
                start = segment.get("start_time")
                if text:
                    timestamp = _format_timestamp(start) or "00:00"
                    transcript_segments.append(f"[{timestamp}] {text}")
        transcript_text = _normalize_text(transcript.text)
        transcript_block = "TRANSCRIPT\n"
        if transcript_text:
            transcript_block += f"- Full transcript: {transcript_text}\n"
        if transcript_segments:
            transcript_block += "- Segments:\n" + "\n".join(f"  {segment}" for segment in transcript_segments) + "\n"
        if not transcript_text and not transcript_segments:
            transcript_block += "- No transcript content available\n"

    summary_block = "SUMMARY\n- No summary available\n"
    if summary:
        summary_lines: list[str] = []
        if summary.overview:
            summary_lines.append(f"Overview: {summary.overview}")
        if summary.main_points:
            summary_lines.append("Main points:\n" + "\n".join(f"- {point}" for point in summary.main_points if point))
        if summary.key_takeaways:
            summary_lines.append("Key takeaways:\n" + "\n".join(f"- {item}" for item in summary.key_takeaways if item))
        summary_block = "SUMMARY\n" + "\n".join(summary_lines) + "\n"

    key_moment_block = "KEY MOMENTS\n- No key moments available\n"
    if key_moments:
        key_moment_lines: list[str] = []
        for moment in key_moments:
            title = _normalize_text(moment.title)
            topic = _normalize_text(moment.topic or "")
            description = _normalize_text(moment.description)
            timestamp = _format_timestamp(moment.start_time) or "00:00"
            fragments = [f"[{timestamp}] {title}"]
            if topic:
                fragments.append(f"Topic: {topic}")
            if description:
                fragments.append(f"Description: {description}")
            key_moment_lines.append("\n".join(fragments))
        key_moment_block = "KEY MOMENTS\n" + "\n".join(f"- {line}" for line in key_moment_lines if line) + "\n"

    return f"""
You are generating MCQs strictly from the supplied video material below.
Use only the information in this video's transcript, summary, and key moments.
Do not use outside knowledge or invent facts.
Do not mix information from other videos.
Do not generate questions that are not supported by the supplied material.

Generate up to 5 high-quality MCQs.
Every question must be grounded in one source section below and must reflect a real concept, fact, process, comparison, cause/effect relationship, or important detail from this video.

Requirements:
- Each question must have exactly 4 options.
- Exactly one option is correct.
- The correct answer must be directly supported by the material.
- Distractors must be plausible but wrong according to the source material.
- The question itself must not be a copied transcript sentence.
- Avoid vague or obvious wording.
- Avoid repeated or near-duplicate questions.
- If the material is weak or ambiguous, do not generate a question.
- Use the exact source labels: "Transcript", "Summary", "Key Moment".
- For transcript and key moment questions, use the relevant timestamp in MM:SS format when available.
- For summary-only questions, use null for timestamp.
- Topic must be concise and specific.
- Difficulty must be one of: "Easy", "Medium", "Hard".
- Return STRICT JSON only as a JSON array of objects.
- No Markdown fences, no commentary, no code block markers, no extra text.

Response object schema:
[
  {{
    "question": "...",
    "options": ["...", "...", "...", "..."],
    "correct_answer": "...",
    "explanation": "...",
    "difficulty": "Easy|Medium|Hard",
    "topic": "...",
    "source": "Transcript|Summary|Key Moment",
    "timestamp": "MM:SS" or null
  }}
]

{transcript_block}
{summary_block}
{key_moment_block}
""".strip()


def _generate_mcqs_with_gemini(video: Video) -> list[dict[str, Any]]:
    client = _get_gemini_client()
    model_name = (settings.gemini_model or "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    response = generate_content_with_retry(
        lambda: client.models.generate_content(
                model=model_name,
                contents=_build_gemini_prompt(video),
                config={
                    "temperature": 0.2,
                    "max_output_tokens": 2000,
                    "response_mime_type": "application/json",
                },
            ),
        operation="mcq_generation",
        model=model_name,
        request_timeout_seconds=GEMINI_SHORT_REQUEST_TIMEOUT_SECONDS,
    )

    if not hasattr(response, "text") or not response.text:
        raise ValueError("Gemini returned no text content.")

    parsed = _extract_json_array(response.text)
    valid_items: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    for item in parsed:
        normalized = _validate_and_normalize_mcq(item, video)
        if normalized is None:
            continue
        question_key = normalized["question"].lower()
        if question_key in seen_questions:
            continue
        seen_questions.add(question_key)
        valid_items.append(normalized)
        if len(valid_items) >= 5:
            break

    if not valid_items:
        raise ValueError("Gemini returned no valid MCQs for the supplied video material.")

    return valid_items


def _legacy_build_expected_mcqs(video: Video) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    fact_map: list[tuple[str, str, Any | None]] = []

    if video.summary:
        for value in [video.summary.overview, *video.summary.main_points, *video.summary.key_takeaways]:
            fact_map.append(("Summary", _normalize_text(value), None))

    if video.transcript and video.transcript.segments:
        for segment in video.transcript.segments:
            if not isinstance(segment, dict):
                continue
            text = _normalize_text(str(segment.get("text", "")))
            if text:
                fact_map.append(("Transcript", text, segment.get("start_time")))

    for moment in video.key_moments or []:
        for value in [moment.topic, moment.title, moment.description]:
            fact_map.append(("Key Moment", _normalize_text(value), moment.start_time))

    unique_fact_map: list[tuple[str, str, Any | None]] = []
    seen: set[tuple[str, str]] = set()
    for source, fact, timestamp in fact_map:
        if not fact:
            continue
        key = (source, fact.lower())
        if key in seen:
            continue
        seen.add(key)
        unique_fact_map.append((source, fact, timestamp))

    for source, fact, timestamp in unique_fact_map:
        question = {
            "question": f"What is the main idea from {source.lower()} material in this video?",
            "options": [fact, "General context", "Secondary detail", "Another fact"],
            "correct_answer": fact,
            "explanation": f"This {source.lower()} material in the selected video emphasizes: {fact}.",
            "difficulty": "Easy" if source == "Summary" else "Medium" if source == "Transcript" else "Hard",
            "topic": source,
            "source": source,
            "timestamp": _format_timestamp(timestamp),
        }
        if len(question["options"]) != 4:
            continue
        questions.append(question)
        if len(questions) >= 5:
            break

    if not questions:
        raise ValueError("No expected MCQ questions could be generated from the available transcript, summary, and key moments.")
    return questions


def build_expected_mcqs(video: Video) -> list[dict[str, Any]]:
    if not settings.gemini_api_key:
        logger.warning("Gemini API key not configured; falling back to legacy MCQ generation for video %s.", video.id)
        return _legacy_build_expected_mcqs(video)

    try:
        return _generate_mcqs_with_gemini(video)
    except GeminiProviderUnavailableError:
        raise
    except Exception as exc:  # pragma: no cover - defensive fallback for missing API or parsing issues.
        logger.warning(
            "Gemini request failed operation=mcq_generation model=%s status_code=%s "
            "provider_status=%s exception_type=%s retry=false final_reason=non_retryable_failure",
            (settings.gemini_model or "gemini-2.5-flash").strip() or "gemini-2.5-flash",
            getattr(exc, "code", getattr(exc, "status_code", None)),
            getattr(exc, "status", None),
            type(exc).__name__,
        )
        raise ValueError(f"MCQ generation failed: {exc}") from exc
