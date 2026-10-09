# Module 3: Explainable Key-Moment Detection

## Input and embeddings

Module 3 accepts the timestamped Whisper transcript segments stored on a video. It keeps valid, non-empty source text with its original `start` and `end`; it never manufactures timestamps. Invalid, negative, reversed, non-finite, or out-of-order segments are ignored.

For normal processing, `sentence-transformers/all-MiniLM-L6-v2` encodes each retained segment into a 384-dimensional sentence embedding. The embedding model is lazy-loaded and cached by `embedding_service`, so repeat requests do not reload it. Neighboring embeddings are compared with cosine similarity, with empty, mismatched, and zero vectors returning a safe `0.0`.

## Topics and keywords

The topic segmenter uses drops in neighbouring cosine similarity as possible boundaries. Its cutoff is the lower of the configured 0.45 ceiling and an adaptive transcript cutoff (`median similarity - max(0.08, 0.5 × standard deviation)`). This treats a boundary as relative evidence rather than a fixed rule. A topic must normally contain at least two chunks; this prevents one-fragment regions. Very short transcripts may use one chunk when semantic evidence supports it.

Labels and keywords are deterministic and transcript-derived. Text is tokenized, punctuation/fillers/stopwords/short tokens are removed, and terms are ranked by corpus frequency multiplied by inverse segment frequency. Labels prefer repeated or strongly relevant two-word phrases, then the best-ranked local content term. Used labels are avoided where another valid local term exists.

## Importance, selection, and storage

Each candidate has a normalized 0–1 importance score:

`0.45 × keyword coverage + 0.30 × content richness + 0.25 × topic relevance`

Keyword coverage measures selected corpus terms in the chunk; richness reaches its maximum at 28 filtered content tokens; topic relevance measures the chunk's filtered vocabulary overlap with its topic region. Each region contributes only its strongest qualifying candidate. Candidates are ranked by score then timestamp. Overlap removal keeps the stronger candidate if their intersection covers at least 25% of the shorter clip, avoiding redundant adjacent highlights.

The generated record stores `video_id`, source `start_time`/`end_time`, title, topic, text, and importance score in `key_moments`. Regeneration replaces only that video's old rows in the same database transaction. Authenticated owners retrieve them with `GET /videos/{video_id}/key-moments`; permitted creators/educators regenerate them with `POST /videos/{video_id}/key-moments/generate`.

If the local embedding dependency or weights cannot load, the service uses the same deterministic transcript-derived keyword and scoring path with one lexical topic region. It creates no fabricated embeddings; production deployments should install the declared Sentence Transformer dependency to receive semantic segmentation.
