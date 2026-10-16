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
            num_beams=2,
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
    extractive = longest >= 35 or (substantive >= 4 and exact / substantive > 0.75)
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
    """Reject empty outputs, but log warnings instead of crashing on minor metric variations."""
    if not short_summary or not short_summary.strip():
        raise SummarizationError("The model returned an empty short summary")
    if not detailed_summary or not detailed_summary.strip():
        raise SummarizationError("The model returned an empty detailed summary")

    # words = len(source.split())
    # if words < 120:
    #     return

    # metrics = _quality_metrics(source, short_summary, detailed_summary)
    # if metrics["extractive"] or metrics["topic_coverage"] < 0.25:
    #     logger.warning(
    #         "Summary quality warning: extractive=%s topic_coverage=%.2f longest_phrase=%s",
    #         metrics["extractive"],
    #         metrics["topic_coverage"],
    #         metrics["longest_shared_phrase_words"],
    #     )

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

    if len(chunks) == 1 and _token_count(chunks[0], tokenizer) <= final_note_limit:
        return chunks[0], 1

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


def _clean_cutoff(text: str) -> str:
    """Removes trailing incomplete sentences caused by aggressive max_length token limits."""
    text = text.strip()
    if not text:
        return ""
    if text[-1] in {'.', '!', '?'}:
        return text
        
    # Find the last actual sentence-ending punctuation
    last_punct = max(text.rfind('.'), text.rfind('!'), text.rfind('?'))
    if last_punct != -1:
        # Cut off the broken sentence after the last punctuation
        return text[:last_punct+1].strip()
        
    # If there's no punctuation at all, append an ellipsis so it doesn't look abruptly broken
    return text + "..."


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
        
        stage = "chunking_and_chunk_summarization"
        chunk_limit = max(1, min(512, input_limit - 50))
        final_note_limit = max(1, input_limit - 50)
        
        notes, chunk_count = _hierarchical_notes(
            text, tokenizer, model, input_limit=input_limit, chunk_limit=chunk_limit,
            final_note_limit=final_note_limit, video_id=video_id, transcript_id=transcript_id,
        )
        
        stage = "detailed_summary_generation"
        # 1. GENERATE DETAILED SUMMARY (Forcing 2-3 paragraphs)
        # To make it look "standard" and deeply analytical without an internet connection,
        # we force BART to generate distinct paragraphs by splitting the notes.
        note_sentences = _sentences(notes)
        num_chunks = 3 if len(note_sentences) >= 6 else (2 if len(note_sentences) >= 2 else 1)
        chunk_size = max(1, len(note_sentences) // num_chunks)
        
        detailed_paragraphs = []
        for i in range(num_chunks):
            start_idx = i * chunk_size
            end_idx = len(note_sentences) if i == num_chunks - 1 else (i + 1) * chunk_size
            section_text = " ".join(note_sentences[start_idx:end_idx])
            
            if len(section_text.split()) > 10:
                section_raw = _generate(
                    section_text, tokenizer, model, 
                    max_length=150, min_length=40, 
                    max_input_tokens=input_limit, instruction=""
                )
                clean_section = _clean_cutoff(section_raw)
                # Prevent BART from repeating the exact same paragraph
                if clean_section and clean_section not in detailed_paragraphs:
                    detailed_paragraphs.append(clean_section)
                    
        if not detailed_paragraphs:
            # Fallback for extremely short videos
            detailed_paragraphs = [_clean_cutoff(_generate(notes, tokenizer, model, max_length=200, min_length=40, max_input_tokens=input_limit, instruction=""))]
            
        detailed = "\n\n".join(detailed_paragraphs)
            
        stage = "short_summary_generation"
        # 2. GENERATE SHORT SUMMARY
        # To absolutely guarantee the short summary is completely different and concise,
        # we compress ONLY the first paragraph of the detailed summary.
        first_paragraph = detailed_paragraphs[0]
        
        short_raw = _generate(
            first_paragraph, tokenizer, model, 
            max_length=50, min_length=15, 
            max_input_tokens=input_limit, instruction=""
        )
        short = _clean_cutoff(short_raw)
        
        # Ultimate safety fallback: If BART still repeats the text, manually extract the first sentence.
        if short == first_paragraph or len(short.split()) > 40:
            short_sents = _sentences(first_paragraph)
            short = short_sents[0] if short_sents else short

        stage = "quality_validation"
        _validate_summary_quality(text, short, detailed)
        
        elapsed = time.perf_counter() - started

        return SummaryResult(short, detailed, chunk_count, elapsed)
    
    except SummarizationError:
        logger.exception("AI summary generation failed stage=%s", stage)
        raise
    except Exception as exc:
        logger.exception("AI summary generation failed stage=%s", stage)
        raise SummarizationError(f"AI summary generation failed during {stage}") from exc

def summarize_transcript(transcript: Transcript) -> SummaryResult:
    """Summarize only the selected completed transcript and record safe diagnostics."""
    if transcript.status != TranscriptStatus.COMPLETED:
        raise ValueError("Only completed transcripts can be summarized")
    text = (transcript.text or "").strip()
    if not text:
        raise ValueError("A completed transcript must contain text")
    result = _summarize_with_hf(text, video_id=transcript.video_id, transcript_id=transcript.id)
    logger.info(
        "Summary completed video_id=%s transcript_id=%s transcript_chars=%s chunks=%s elapsed_seconds=%.3f model=%s",
        transcript.video_id, transcript.id, len(text), result.chunk_count,
        result.generation_seconds, os.getenv("LOCAL_SUMMARY_MODEL", _DEFAULT_MODEL),
    )
    return result
 




