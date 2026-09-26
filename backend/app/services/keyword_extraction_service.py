"""Local semantic keyphrase extraction shared by Module 3 and analytics.

KeyBERT scores candidate phrases against the source document with the same
Sentence Transformer used by topic segmentation. A deterministic lexical
fallback is used only when the local model/package cannot be loaded.
"""
from __future__ import annotations

from collections import Counter
import logging
import os
import re
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_STOP_WORDS = {
    "a", "about", "after", "again", "also", "am", "an", "and", "any", "are", "as", "at",
    "be", "because", "been", "before", "being", "but", "by", "can", "could", "did", "do",
    "does", "doing", "down", "during", "each", "few", "for", "from", "further", "had",
    "has", "have", "having", "he", "her", "here", "hers", "herself", "him", "himself",
    "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me",
    "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which",
    "while", "who", "whom", "why", "will", "with", "would", "you", "your", "yours",
    "yourself", "yourselves", "um", "uh", "okay", "ok", "yeah", "right", "like", "well",
}
_FILLER = {"know", "yes", "yep", "nope", "sure", "exactly", "great", "hello", "hi", "thanks", "thank"}


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    words = re.findall(r"[\w'-]+", text, flags=re.UNICODE)
    meaningful = [word for word in words if word.casefold() not in _STOP_WORDS | _FILLER and len(word) > 2]
    return text if len(meaningful) >= 2 else ""


def _normalize_rows(rows: Any, top_n: int) -> list[dict[str, float | str]]:
    seen: set[str] = set()
    result: list[dict[str, float | str]] = []
    for phrase, raw_score in rows or []:
        phrase = re.sub(r"\s+", " ", str(phrase)).strip(" .,:;\t\n")
        key = phrase.casefold()
        words = re.findall(r"[\w'-]+", phrase, flags=re.UNICODE)
        if not phrase or key in seen or not words or all(w.casefold() in _STOP_WORDS | _FILLER for w in words):
            continue
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            continue
        if not (score == score and abs(score) != float("inf")):
            continue
        seen.add(key)
        result.append({"phrase": phrase, "score": round(max(0.0, min(1.0, score)), 4)})
        if len(result) >= top_n:
            break
    return result


def _lexical_fallback(text: str, top_n: int) -> list[dict[str, float | str]]:
    tokens = [w.casefold() for w in re.findall(r"[\w'-]+", text, flags=re.UNICODE)]
    tokens = [w for w in tokens if len(w) > 2 and w not in _STOP_WORDS | _FILLER and not w.isnumeric()]
    candidates = Counter()
    for size in (3, 2, 1):
        for index in range(max(0, len(tokens) - size + 1)):
            phrase = " ".join(tokens[index:index + size])
            if len(phrase.split()) == size:
                candidates[phrase] += 1
    ranked = sorted(candidates.items(), key=lambda item: (-item[1] * len(item[0].split()), -item[1], item[0]))
    rows = [(phrase, count / max(1, len(tokens))) for phrase, count in ranked]
    return _normalize_rows(rows, top_n)


@lru_cache(maxsize=1)
def _load_keybert():
    from keybert import KeyBERT
    from app.services.embedding_service import load_embedding_model

    model_name = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    return KeyBERT(model=load_embedding_model(model_name))


def extract_keyphrases(
    text: str,
    *,
    top_n: int | None = None,
    ngram_range: tuple[int, int] | None = None,
    use_mmr: bool | None = None,
    diversity: float | None = None,
) -> list[dict[str, float | str]]:
    """Return unique source-grounded phrase/score pairs using local KeyBERT."""
    requested_top_n = top_n if top_n is not None else int(os.getenv("KEYWORD_TOP_N", "10"))
    requested_top_n = max(1, min(50, requested_top_n))
    clean = _clean(text)
    if not clean:
        return []
    ngrams = ngram_range or (
        int(os.getenv("KEYWORD_NGRAM_MIN", "1")),
        int(os.getenv("KEYWORD_NGRAM_MAX", "3")),
    )
    mmr = use_mmr if use_mmr is not None else os.getenv("KEYWORD_USE_MMR", "true").lower() == "true"
    diversity_value = diversity if diversity is not None else float(os.getenv("KEYWORD_MMR_DIVERSITY", "0.5"))
    diversity_value = max(0.0, min(1.0, diversity_value))
    try:
        model = _load_keybert()
        rows = model.extract_keywords(
            clean,
            keyphrase_ngram_range=ngrams,
            stop_words="english",
            top_n=requested_top_n,
            use_mmr=mmr,
            diversity=diversity_value,
        )
        normalized = _normalize_rows(rows, requested_top_n)
        if normalized:
            return normalized
    except Exception:
        logger.exception("Local KeyBERT extraction failed; using deterministic lexical fallback")
    return _lexical_fallback(clean, requested_top_n)

