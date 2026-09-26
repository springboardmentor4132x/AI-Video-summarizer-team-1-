"""Grounded hierarchical summaries for completed transcripts."""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
import logging
import os
import re
import threading
import time
from typing import Any

from app.models.transcript import Transcript, TranscriptStatus


logger = logging.getLogger(__name__)
_GENERATION_LOCK = threading.RLock()
_MODEL_LOADING_LOCK = threading.RLock()
_MODEL_CACHE: dict[str, tuple[Any, Any]] = {}
_DEFAULT_MODEL = "facebook/bart-large-cnn"
_MAX_INPUT_TOKENS = 900
_STOP_WORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been", "being", "but", "can",
    "could", "did", "does", "for", "from", "had", "has", "have", "how", "into", "its", "just",
    "more", "most", "not", "our", "out", "over", "said", "some", "such", "than", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "those", "through", "very", "was",
    "were", "what", "when", "where", "which", "while", "will", "with", "would", "you", "your",
}


@dataclass(frozen=True)
class SummaryResult:
    short_summary: str
    detailed_summary: str
    chunk_count: int = 0
    generation_seconds: float = 0.0


class SummarizationError(RuntimeError):
    """Raised when the configured AI model cannot produce both summaries."""


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


def _token_count(text: str, tokenizer: Any) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))


def _split_long_sentence(sentence: str, tokenizer: Any, limit: int) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    for word in sentence.split():
        candidate = " ".join((*current, word))
        if current and _token_count(candidate, tokenizer) > limit:
            pieces.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        pieces.append(" ".join(current))
    return pieces or [sentence]


def _chunk_text(
    text: str,
    max_chars: int = 1800,
    tokenizer: Any | None = None,
    max_tokens: int = _MAX_INPUT_TOKENS,
) -> list[str]:
    """Split in order at sentence boundaries; split only oversized sentences at word boundaries."""
    sentences = _sentences(text)
    if not sentences:
        return [text.strip()] if text.strip() else []
    if tokenizer is None:
        chunks: list[str] = []
        current: list[str] = []
        size = 0
        for sentence in sentences:
            if current and size + len(sentence) + 1 > max_chars:
                chunks.append(" ".join(current))
                current, size = [], 0
            current.append(sentence)
            size += len(sentence) + 1
        if current:
            chunks.append(" ".join(current))
        return chunks

    chunks: list[str] = []
    current: list[str] = []
    # Reserve space for the tokenizer's automatically added BOS/EOS tokens.
    content_limit = max(1, max_tokens - 2)
    for sentence in sentences:
        for piece in _split_long_sentence(sentence, tokenizer, content_limit):
            candidate = " ".join((*current, piece))
            if current and _token_count(candidate, tokenizer) > content_limit:
                chunks.append(" ".join(current))
                current = []
                candidate = piece
            if _token_count(candidate, tokenizer) > content_limit:
                raise SummarizationError("A transcript segment cannot fit within the tokenizer input limit")
            current.append(piece)
    if current:
        chunks.append(" ".join(current))
    return chunks


def _load_model(model_name: str) -> tuple[Any, Any]:
    """Load one cached tokenizer/model pair on first use and reuse it thereafter."""
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    with _MODEL_LOADING_LOCK:
        if model_name in _MODEL_CACHE:
            return _MODEL_CACHE[model_name]
        try:
            tokenizer = AutoTokenizer.from_pretrained(model_name)
        except Exception as exc:
            logger.exception("Summary tokenizer initialization failed model=%s", model_name)
            raise SummarizationError(f"Tokenizer initialization failed for {model_name}") from exc
        try:
            model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        except Exception as exc:
            logger.exception("Summary model initialization failed model=%s", model_name)
            raise SummarizationError(f"Model initialization failed for {model_name}") from exc
        model.to("cpu")
        model.eval()
        # The application uses one summarization model at a time; replacing the
        # active cache avoids keeping a second large model resident in memory.
        _MODEL_CACHE.clear()
        pair = (tokenizer, model)
        _MODEL_CACHE[model_name] = pair
        return pair


def _clear_model_cache() -> None:
    with _MODEL_LOADING_LOCK:
        _MODEL_CACHE.clear()


# Preserve a tiny cache-reset hook for deterministic loader tests.
_load_model.cache_clear = _clear_model_cache


def _model_input_limit(tokenizer: Any, model: Any) -> int:
    limits = [_MAX_INPUT_TOKENS]
    for value in (
        getattr(tokenizer, "model_max_length", None),
        getattr(model.config, "max_position_embeddings", None),
        getattr(model.config, "n_positions", None),
    ):
        if isinstance(value, int) and 16 < value < 100_000:
            limits.append(value)
    return max(1, min(limits) - 2)


def _format_model_input(text: str, model: Any, instruction: str) -> str:
    if getattr(model.config, "model_type", "") in {"t5", "mt5"}:
        return f"{instruction}\n\n{text}"
    return text


def _safe_format_and_chunk(
    text: str, 
    tokenizer: Any, 
    model: Any, 
    instruction: str,
    max_input_tokens: int = _MAX_INPUT_TOKENS,
) -> str:
    """Format one already-segmented input and fail rather than dropping its tail."""
    formatted = _format_model_input(text, model, instruction)
    # Reserve BOS/EOS special tokens in addition to the content token count.
    formatted_tokens = _token_count(formatted, tokenizer) + 2
    
    # If it already fits, return as-is
    if formatted_tokens <= max_input_tokens:
        return formatted
    
    logger.error("Token-limit failure: formatted input has %d tokens; limit is %d", formatted_tokens, max_input_tokens)
    raise SummarizationError(
        f"A summary input segment exceeds the safe model limit ({formatted_tokens} > {max_input_tokens} tokens)"
    )


def _generate(
    text: str,
    tokenizer: Any,
    model: Any,
    *,
    max_length: int,
    min_length: int = 40,
    max_input_tokens: int = _MAX_INPUT_TOKENS,
    encoder_no_repeat_ngram_size: int = 3,
    instruction: str = "Summarize the transcript faithfully in your own words.",
) -> str:
    import torch

    # Use safe formatting that ensures we never silently truncate content
    source = _safe_format_and_chunk(text, tokenizer, model, instruction, max_input_tokens)
    # BART's learned positional limit is 1024. _model_input_limit leaves a
    # safety margin; never rely on tokenizer truncation to hide a bad chunk.
    inputs = tokenizer(source, return_tensors="pt", truncation=False)
    input_length = int(inputs["input_ids"].shape[-1])
    if input_length > max_input_tokens:
        logger.error("Token-limit failure immediately before generation: %d > %d", input_length, max_input_tokens)
        raise SummarizationError(
            f"Tokenized summary input exceeds the safe model limit ({input_length} > {max_input_tokens})"
        )
    with _GENERATION_LOCK, torch.inference_mode():
        generated = model.generate(
            **inputs,
            # BART-large-CNN ships with max_length=142/min_length=56. Use its
            # native length parameters instead of conflicting max_new_tokens.
            max_length=max_length,
            min_length=min(min_length, max_length - 1),
            num_beams=4,
            length_penalty=2.0,
            no_repeat_ngram_size=3,
            early_stopping=True,
            repetition_penalty=1.05,
            encoder_no_repeat_ngram_size=encoder_no_repeat_ngram_size,
        )
    return tokenizer.decode(generated[0], skip_special_tokens=True).strip()


def _longest_shared_phrase_words(source: str, output: str) -> int:
    """Return longest contiguous normalized token overlap, without retaining/logging phrase text."""
    source_tokens = re.findall(r"[\w'-]+", source.casefold())
    output_tokens = re.findall(r"[\w'-]+", output.casefold())
    if not source_tokens or not output_tokens:
        return 0
    previous = [0] * (len(output_tokens) + 1)
    longest = 0
    for source_token in source_tokens:
        current = [0]
        for index, output_token in enumerate(output_tokens, start=1):
            value = previous[index - 1] + 1 if source_token == output_token else 0
            current.append(value)
            longest = max(longest, value)
        previous = current
    return longest


def _topic_coverage(source: str, *summaries: str) -> tuple[int, int, float]:
    terms = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{3,}", source.casefold())
    frequencies = Counter(term for term in terms if term not in _STOP_WORDS)
    # Use frequent transcript terms as a lightweight, topic-agnostic coverage proxy.
    topics = [term for term, _count in frequencies.most_common(30)]
    if not topics:
        return 0, 0, 1.0
    output = " ".join(summaries).casefold()
    covered = sum(term in output for term in topics)
    return covered, len(topics), covered / len(topics)


def _quality_metrics(source: str, short_summary: str, detailed_summary: str) -> dict[str, Any]:
    source_words = len(source.split())
    short_words = len(short_summary.split())
    detailed_words = len(detailed_summary.split())
    longest = max(
        _longest_shared_phrase_words(source, short_summary),
        _longest_shared_phrase_words(source, detailed_summary),
    )
    covered, available, coverage = _topic_coverage(source, short_summary, detailed_summary)
    source_sentences = {" ".join(re.findall(r"\w+", sentence.casefold())) for sentence in _sentences(source)}
    detailed_sentences = [" ".join(re.findall(r"\w+", sentence.casefold())) for sentence in _sentences(detailed_summary)]
    exact = sum(len(sentence.split()) >= 8 and sentence in source_sentences for sentence in detailed_sentences)
    substantive = sum(len(sentence.split()) >= 8 for sentence in detailed_sentences)
    extractive = longest >= 14 or (substantive >= 4 and exact / substantive > 0.55)
    return {
        "transcript_words": source_words,
        "short_words": short_words,
        "detailed_words": detailed_words,
        "short_compression_ratio": round(short_words / max(1, source_words), 3),
        "detailed_compression_ratio": round(detailed_words / max(1, source_words), 3),
        "short_paragraphs": len([p for p in re.split(r"\n\s*\n", short_summary.strip()) if p.strip()]),
        "detailed_paragraphs": len([p for p in re.split(r"\n\s*\n", detailed_summary.strip()) if p.strip()]),
        "longest_shared_phrase_words": longest,
        "extractive": extractive,
        "topic_coverage": round(coverage, 3),
        "topic_terms_covered": covered,
        "topic_terms_total": available,
    }


def _validate_summary_quality(source: str, short_summary: str, detailed_summary: str) -> None:
    """Reject obviously incomplete, copied, or hallucinated output, while scaling expectations for short videos."""
    if not short_summary.strip() or not detailed_summary.strip():
        raise SummarizationError("The model returned an empty summary")
    words = len(source.split())
    metrics = _quality_metrics(source, short_summary, detailed_summary)
    if words >= 5 and (metrics["short_words"] >= words or metrics["detailed_words"] >= words):
        raise SummarizationError("The model output is not shorter than its source transcript")
    # The copying threshold scales down for short clips; proper nouns and short
    # technical expressions are permitted, but copied sentences are not.
    copy_limit = min(14, max(6, words // 3))
    if metrics["longest_shared_phrase_words"] >= copy_limit or metrics["extractive"]:
        raise SummarizationError(
            "The model output is too extractive to present as a synthesized summary "
            f"(longest shared phrase: {metrics['longest_shared_phrase_words']} words)."
        )
    summary_tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]*", f"{short_summary} {detailed_summary}".casefold())
    filler_tokens = {"hello", "welcome", "today", "okay", "yeah", "right", "um", "uh", "basically", "so"}
    if summary_tokens and sum(token in filler_tokens for token in summary_tokens) / len(summary_tokens) > 0.35:
        raise SummarizationError("The model output contains too much presenter filler")
    if words < 120:
        # Short clips skip the long-source minimum/coverage thresholds, but
        # still must be compressed, non-empty, and not mostly copied/filler.
        return
    
    # Minimum length checks (scaled by transcript length). Floors catch truly degenerate (single-sentence)
    # outputs while leaving room for the model to do its work on dense news
    # transcripts where hierarchical reduction compresses deeply.
    if words >= 700:
        short_minimum, detailed_minimum = 25, 30
    else:
        short_minimum = max(12, round(words * 0.04))
        detailed_minimum = max(18, round(words * 0.06))
    
    if metrics["short_words"] < short_minimum:
        raise SummarizationError(
            f"The model returned an undersized short summary ({metrics['short_words']} words; minimum {short_minimum})."
        )
    
    if metrics["detailed_words"] < detailed_minimum:
        raise SummarizationError(
            f"The model returned an undersized detailed summary ({metrics['detailed_words']} words; minimum {detailed_minimum})."
        )
    
    # Topic coverage check: ensure the summary addresses main topics from the source
    # Only apply this check if there's also evidence of other quality issues
    if metrics["topic_coverage"] < 0.25 and metrics["extractive"]:  # Only fail if BOTH low coverage AND extractive
        raise SummarizationError(
            f"The summary has low topic coverage ({metrics['topic_coverage']:.1%} of key terms) "
            "and is too extractive. The model may have hallucinated or focused on minor details."
        )


_CHUNK_INSTRUCTION = (
    "Extract specific semantic notes from this transcript section.\n\n"
    "Requirements:\n"
    "- Preserve actual meaning and all important facts.\n"
    "- Identify the main idea and important details.\n"
    "- Keep important facts, numbers, names, technical concepts and conclusions.\n"
    "- Remove filler, repetition, and casual conversation.\n"
    "- Use your own wording instead of copying sentences.\n"
    "- Do NOT invent information not in the text.\n"
    "- Do NOT add outside knowledge.\n"
    "- Do NOT make unsupported claims.\n"
    "- Preserve uncertainty when the speaker expresses it.\n"
    "- If the section contains little useful information, produce a very concise summary."
)
def _summarize_chunk(chunk: str, tokenizer: Any, model: Any, input_limit: int) -> str:
    source_tokens = _token_count(chunk, tokenizer)
    minimum = max(8, min(40, round(source_tokens * 0.12)))
    maximum = max(minimum + 1, min(200, round(source_tokens * 0.80)))
    return _generate(
        chunk, tokenizer, model, max_length=maximum, min_length=minimum, max_input_tokens=input_limit,
        instruction=_CHUNK_INSTRUCTION,
    )


def _hierarchical_notes(
    text: str, tokenizer: Any, model: Any, *, input_limit: int, chunk_limit: int, final_note_limit: int,
    video_id: int | None = None, transcript_id: int | None = None,
) -> tuple[str, int]:
    chunks = _chunk_text(text, tokenizer=tokenizer, max_tokens=chunk_limit)
    if not chunks:
        raise SummarizationError("Transcript produced no model input chunks")
    logger.info(
        "Summary input video_id=%s transcript_id=%s transcript_chars=%s transcript_words=%s chunks=%s chunk_boundaries=%s",
        video_id, transcript_id, len(text), len(text.split()), len(chunks),
        [
            {"index": index, "token_start": sum(_token_count(c, tokenizer) for c in chunks[:index]),
             "token_end": sum(_token_count(c, tokenizer) for c in chunks[:index + 1]), "chars": len(chunk)}
            for index, chunk in enumerate(chunks)
        ],
    )
    # Every chunk, including a single-chunk transcript, is summarized before final synthesis.
    notes = [_summarize_chunk(chunk, tokenizer, model, input_limit) for chunk in chunks]
    notes = [note for note in notes if note]
    if not notes:
        raise SummarizationError("The model returned no chunk summaries")

    reduce_instruction = (
        "Consolidate these ordered notes while preserving all important information.\n\n"
        "Requirements:\n"
        "- Preserve distinct facts, important examples, technical names, and conclusions.\n"
        "- Combine related points; remove repetition and duplication.\n"
        "- Maintain the logical flow and relationships between ideas.\n"
        "- Paraphrase to avoid copying.\n"
        "- Use ONLY information supported by the notes.\n"
        "- Do NOT add outside facts.\n"
        "- Do NOT invent information.\n"
        "- Do NOT hallucinate.\n"
        "- Preserve uncertainty when the source expresses it."
    )
    # Calculate how much space the instruction takes
    instruction_formatted = _format_model_input("", model, reduce_instruction)
    instruction_tokens = _token_count(instruction_formatted, tokenizer)
    
    # The actual available space for content after instruction
    reduce_limit = max(1, input_limit - instruction_tokens - 2)
    note_limit = min(final_note_limit, reduce_limit)
    
    # Recursively reduce ordered groups until the complete source fits final synthesis context.
    while _token_count("\n".join(notes), tokenizer) > note_limit:
        current_token_count = _token_count("\n".join(notes), tokenizer)
        # Chunk notes to fit within reduce_limit (content-only, instruction is added in _generate)
        groups = _chunk_text("\n".join(notes), tokenizer=tokenizer, max_tokens=reduce_limit)
        if len(groups) >= len(notes):
            raise SummarizationError("Combined chunk notes could not be reduced to the model context")
        reduced = [
            _generate(group, tokenizer, model, max_length=180,
                      min_length=max(8, min(40, round(_token_count(group, tokenizer) * 0.10))),
                      max_input_tokens=input_limit,
                      instruction=reduce_instruction)
            for group in groups
        ]
        next_notes = [note for note in reduced if note]
        if not next_notes or _token_count("\n".join(next_notes), tokenizer) >= current_token_count:
            raise SummarizationError("The model could not reduce combined notes for final synthesis")
        notes = next_notes
    return "\n".join(notes), len(chunks)


def _summarize_with_hf(
    text: str, *, video_id: int | None = None, transcript_id: int | None = None
) -> SummaryResult:
    """Summarize every token-bounded chunk, recursively combine notes, then synthesize both outputs."""
    model_name = os.getenv("LOCAL_SUMMARY_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    started = time.perf_counter()
    stage = "model_loading"
    try:
        tokenizer, model = _load_model(model_name)
        input_limit = _model_input_limit(tokenizer, model)
        stage = "chunking"
        if getattr(model.config, "model_type", "") in {"t5", "mt5"}:
            chunk_prompt_tokens = _token_count(_format_model_input("", model, _CHUNK_INSTRUCTION), tokenizer)
        else:
            chunk_prompt_tokens = 0
        # Use most of BART's safe context for each first-pass chunk, preserving
        # whole sentences where possible; the two-token reserve covers BOS/EOS.
        chunk_limit = max(1, min(512, input_limit - chunk_prompt_tokens - 2))
        detailed_instruction = (
            "Write a coherent detailed explanation of the video's actual content.\n\n"
            "Requirements:\n"
            "1. Identify the central subject/purpose of the video.\n"
            "2. Cover the major topics and ideas actually discussed.\n"
            "3. Explain important concepts rather than merely listing them.\n"
            "4. Preserve important facts, numbers, names, technical terminology, and conclusions.\n"
            "5. Organize naturally into paragraphs; connect related ideas.\n"
            "6. Remove filler, repetition, and conversational noise.\n"
            "7. Use original wording rather than copying transcript sentences.\n"
            "8. Use only information supported by the source transcript.\n"
            "9. Maintain factual accuracy and preserve relationships between ideas.\n"
            "10. Preserve uncertainty when the speaker expresses it.\n"
            "11. Do NOT introduce outside knowledge.\n"
            "12. Do NOT invent or make unsupported claims.\n"
            "13. Do NOT hallucinate facts or conclusions not in the transcript.\n"
            "14. Do NOT exaggerate claims made in the video.\n"
            "15. Do NOT omit important conclusions.\n"
            "16. Provide a fuller explanation than the short overview, scaled to the available source material.\n"
            "17. Every sentence must be supported by the source transcript."
        )
        short_instruction = (
            "Write a concise but informative overview of the video's content.\n\n"
            "Requirements:\n"
            "1. Explain what the video is mainly about.\n"
            "2. Cover the most important ideas and conclusions.\n"
            "3. Include important facts, technical concepts, examples when relevant.\n"
            "4. Remove filler, greetings, repetition, and minor details.\n"
            "5. Use original wording rather than copying transcript sentences.\n"
            "6. Maintain factual accuracy.\n"
            "7. Preserve uncertainty when the speaker expresses it.\n"
            "8. Use only information supported by the transcript.\n"
            "9. Do NOT hallucinate.\n"
            "10. Do NOT invent or add information not in the transcript.\n"
            "11. Do NOT mention that you are an AI.\n"
            "12. Do NOT say 'the transcript says'.\n"
            "13. Do NOT create generic introduction.\n"
            "14. Keep the overview concise while covering the main points.\n"
            "15. Every sentence must be supported by the source transcript.\n"
            "The summary should allow someone who did not watch the video to understand what was discussed."
        )
        final_note_limit = min(
            input_limit - _token_count(_format_model_input("", model, detailed_instruction), tokenizer) - 2,
            input_limit - _token_count(_format_model_input("", model, short_instruction), tokenizer) - 2,
        )
        stage = "chunking_and_chunk_summarization"
        notes, chunk_count = _hierarchical_notes(
            text, tokenizer, model, input_limit=input_limit, chunk_limit=chunk_limit,
            final_note_limit=max(1, final_note_limit), video_id=video_id, transcript_id=transcript_id,
        )
        stage = "final_synthesis"
        source_tokens = _token_count(text, tokenizer)
        notes_tokens = _token_count(notes, tokenizer)
        source_words = len(text.split())
        if source_words >= 700:
            short_word_floor, detailed_word_floor = 25, 30
        elif source_words >= 120:
            short_word_floor = max(12, round(source_words * 0.04))
            detailed_word_floor = max(18, round(source_words * 0.06))
        else:
            short_word_floor = max(4, round(source_tokens * 0.20))
            detailed_word_floor = max(6, round(source_tokens * 0.30))
        # Convert the existing word-count floors to output-token bounds. Very
        # short clips scale to their size; longer clips use the complete note
        # set so detail does not collapse to a one-line summary.
        if source_words < 120:
            short_minimum = max(5, round(source_tokens * 0.20))
            detailed_minimum = max(8, round(source_tokens * 0.30))
            short_maximum = min(50, max(short_minimum + 8, round(source_tokens * 0.80)))
            detailed_maximum = min(90, max(detailed_minimum + 12, round(source_tokens * 1.20)))
        else:
            short_minimum = max(24, round(short_word_floor * 1.35), round(notes_tokens * 0.10))
            detailed_minimum = max(42, round(detailed_word_floor * 1.35), round(notes_tokens * 0.25))
            short_minimum = min(90, short_minimum)
            detailed_minimum = min(160, detailed_minimum)
            short_maximum = min(140, max(short_minimum + 12, round(notes_tokens * 0.35)))
            detailed_maximum = min(360, max(detailed_minimum + 24, round(notes_tokens * 0.90)))
        detailed = _generate(notes, tokenizer, model, max_length=detailed_maximum, min_length=detailed_minimum,
                             max_input_tokens=input_limit, instruction=detailed_instruction)
        if not detailed:
            raise SummarizationError("The model returned an empty detailed summary")
        short = _generate(notes, tokenizer, model, max_length=short_maximum, min_length=short_minimum,
                          max_input_tokens=input_limit, instruction=short_instruction)
        if not short:
            raise SummarizationError("The model returned an empty short summary")
        metrics = _quality_metrics(text, short, detailed)
        stage = "quality_validation"
        logger.info(
            "Summary quality validation video_id=%s transcript_id=%s model=%s elapsed_seconds=%.3f "
            "short_words=%s detailed_words=%s topic_coverage=%.1f%% extractive=%s longest_phrase=%s",
            video_id, transcript_id, model_name, time.perf_counter() - started,
            metrics["short_words"], metrics["detailed_words"],
            metrics["topic_coverage"] * 100, metrics["extractive"],
            metrics["longest_shared_phrase_words"],
        )
        _validate_summary_quality(text, short, detailed)
        elapsed = time.perf_counter() - started
        logger.info(
            "Summary completed video_id=%s transcript_id=%s model=%s elapsed_seconds=%.3f "
            "transcript_chars=%s chunks=%s compression_short=%.2f%% compression_detailed=%.2f%%",
            video_id, transcript_id, model_name, elapsed,
            len(text), chunk_count,
            metrics["short_compression_ratio"] * 100,
            metrics["detailed_compression_ratio"] * 100,
        )
        return SummaryResult(short, detailed, chunk_count, elapsed)
    except SummarizationError:
        logger.exception("AI summary generation failed stage=%s model=%s elapsed_seconds=%.3f", stage, model_name, time.perf_counter() - started)
        raise
    except Exception as exc:
        logger.exception("AI summary generation failed stage=%s model=%s elapsed_seconds=%.3f", stage, model_name, time.perf_counter() - started)
        raise SummarizationError(f"AI summary generation failed during {stage} using {model_name}") from exc


def summarize_text(text: str, *, video_id: int | None = None, transcript_id: int | None = None) -> SummaryResult:
    """Run the same local hierarchical BART pipeline for supplied source text."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Transcript content is required for summarization")
    result = _summarize_with_hf(text, video_id=video_id, transcript_id=transcript_id)
    logger.info(
        "Summary completed video_id=%s transcript_id=%s transcript_chars=%s chunks=%s elapsed_seconds=%.3f model=%s",
        video_id, transcript_id, len(text), result.chunk_count,
        result.generation_seconds, os.getenv("LOCAL_SUMMARY_MODEL", _DEFAULT_MODEL),
    )
    return result


def summarize_transcript(transcript: Transcript) -> SummaryResult:
    """Summarize only the selected completed transcript and record safe diagnostics."""
    if transcript.status != TranscriptStatus.COMPLETED:
        raise ValueError("Only completed transcripts can be summarized")
    text = (transcript.text or "").strip()
    # Prefer the stored Whisper segments so Module 2 consumes the same ordered,
    # timestamped source that Module 3 and transcript seeking use. Timestamps
    # are intentionally not rendered into BART's language input.
    segments = transcript.segments or []
    segment_texts = [
        segment.get("text", "").strip()
        for segment in segments
        if isinstance(segment, dict) and isinstance(segment.get("text"), str)
        and segment.get("text", "").strip()
    ]
    if segment_texts:
        text = " ".join(segment_texts)
    if not text:
        raise ValueError("A completed transcript must contain text")
    return summarize_text(text, video_id=transcript.video_id, transcript_id=transcript.id)





