# Module 3: Explainable Key-Moment Detection

## Input and embeddings

Module 3 accepts the timestamped Whisper transcript segments stored on a video. It keeps valid, non-empty source text with its original `start` and `end`; it never manufactures timestamps. Invalid, negative, reversed, non-finite, or out-of-order segments are ignored.

For normal processing, `sentence-transformers/all-MiniLM-L6-v2` encodes each retained segment into a 384-dimensional sentence embedding. The embedding model is lazy-loaded and cached by `embedding_service`, so repeat requests do not reload it. Neighboring embeddings are compared with cosine similarity, with empty, mismatched, and zero vectors returning a safe `0.0`.

## Topics and keywords

The topic segmenter uses drops in neighbouring cosine similarity as possible boundaries. Its cutoff is the lower of the configured 0.45 ceiling and an adaptive transcript cutoff (`median similarity - max(0.08, 0.5 × standard deviation)`). This treats a boundary as relative evidence rather than a fixed rule. A topic must normally contain at least two chunks; this prevents one-fragment regions. Very short transcripts may use one chunk when semantic evidence supports it.

Key phrases are extracted with local KeyBERT using the same cached `all-MiniLM-L6-v2` embeddings. Candidate phrases use n-grams of one to three words, English stopword filtering, `top_n=10`, and maximal marginal relevance (MMR) with diversity 0.5. The returned cosine relevance values are normalized to 0–1 and are relevance signals, not probabilities. Duplicate, empty, and filler-only candidates are discarded. Topic labels prefer a source-grounded KeyBERT phrase that occurs in the region, then a non-generic local term, and finally `General Discussion`. If model loading fails, deterministic TF/IDF-style token ranking is used as a clearly limited fallback.

## Importance, selection, and storage

Each candidate has a heuristic 0–1 importance/relevance score (not a probability):

`0.45 × keyword coverage + 0.30 × content richness + 0.25 × topic relevance`

Keyword coverage measures selected phrase terms in the candidate; richness reaches its maximum at 28 filtered content tokens; topic relevance measures the candidate's filtered vocabulary overlap with its topic region. A candidate must contain at least four content tokens and three distinct terms after filler filtering. Candidate windows expand from Whisper segment boundaries until they have useful context, normally at least 6 seconds, and are capped at 35 seconds; source timestamps are retained and are never estimated. These defaults can be overridden with `KEY_MOMENT_MIN_SECONDS` and `KEY_MOMENT_MAX_SECONDS`.

The segmenter confirms boundaries using a sharp local similarity drop or sustained low similarity and merges undersized regions. Up to three strong windows per topic are considered. Expanded windows undergo overlap removal again, then are selected round-robin by topic before remaining high-ranked candidates are added. This balances relevance with coverage and avoids a list dominated by one topic.

The generated record stores `video_id`, source `start_time`/`end_time`, title, topic, text, and importance score in `key_moments`. Regeneration replaces only that video's old rows in the same database transaction. Authenticated owners retrieve them with `GET /videos/{video_id}/key-moments`; permitted creators/educators regenerate them with `POST /videos/{video_id}/key-moments/generate`.

For explainability, inspect the stored transcript text and timestamps, topic label, keyphrase overlap, content density, topic fit, and final score. Analytics applies the same KeyBERT extractor per transcript and counts each phrase once per transcript; it does not label these counts as model confidence. If local model weights or KeyBERT cannot load, the service uses a deterministic transcript-derived lexical fallback and one lexical topic region. It creates no fabricated embeddings; install the declared KeyBERT and Sentence Transformer dependencies and model weights for semantic extraction and segmentation.
