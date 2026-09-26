# ClipMind AI processing: inputs, algorithms, and outputs

ClipMind keeps inference local. The backend uses FastAPI and PostgreSQL; media is processed with FFmpeg, transcription with Whisper, summary generation with BART, and semantic analysis with Sentence Transformers and KeyBERT. The stages use persisted video/transcript records and their source timestamps.

## Upload and speech recognition

1. **Input:** an authenticated creator's uploaded video file.
2. **FFmpeg:** validates/transcodes media and extracts an audio track for recognition and source media for playback/highlights.
3. **Whisper:** consumes the extracted audio and recognizes speech locally.
4. **Output:** language, transcript text, and timestamped speech segments are stored against the owning video in PostgreSQL. The Whisper segment times remain the source for transcript seeking and highlight boundaries.

## BART summary generation

1. **Input:** the completed stored transcript (`facebook/bart-large-cnn` by default; override only through `LOCAL_SUMMARY_MODEL`).
2. **Cleaning:** normalize whitespace and split at sentence boundaries; exceptionally long sentences are split at word boundaries. Token counts are checked before inference to prevent silent truncation.
3. **Chunk summaries:** BART writes grounded notes for every source chunk, preserving facts and removing filler. Ordered notes are recursively reduced when they exceed the final model context.
4. **Final synthesis:** BART generates a concise short summary and a longer detailed summary from the reduced notes, with instructions to use only transcript-supported information.
5. **Validation:** non-empty outputs, minimum sizes for long sources, compression, repeated/copying indicators, and source topic coverage are measured. These are heuristic quality checks, not factuality scores; they cannot prove that a model output contains no hallucination. Rejected output is surfaced as a generation failure rather than shown as a successful summary.
6. **Output:** short and detailed summaries and their generation status/time are stored with the transcript. No external AI API is called. The short summary is the current abstraction of the video's central message; a separate persisted takeaways field is not currently part of the database schema.

## Module 3: topics and key moments

1. **Input:** Whisper segments with original timestamps.
2. **Segmentation:** discard invalid timestamps and empty text, then retain segment boundaries. `all-MiniLM-L6-v2` creates one embedding per retained segment.
3. **Cosine similarity:** compare neighboring vectors as `dot(a,b) / (||a|| × ||b||)`. A similarity decrease signals a possible boundary; a sharp local drop or sustained low similarity must corroborate it. Minimum topic size merges tiny regions.
4. **Keyphrase extraction:** local KeyBERT compares one-to-three-word transcript candidates with their document embedding and uses MMR (diversity 0.5) to reduce redundant phrases. The same service powers analytics. Phrase scores are relevance signals, not probabilities. A deterministic lexical fallback is used if local model loading fails.
5. **Topic labels:** use meaningful KeyBERT phrases found in the actual region, then non-generic local terms. `General Discussion` is the safe fallback when no useful label is available.
6. **Candidate windows:** reject filler-only and low-information text. Expand useful source segments into contextual windows, normally at least 6 seconds and no more than 35 seconds, using the original Whisper timestamps.
7. **Importance score:**

   `0.45 × keyphrase coverage + 0.30 × content density + 0.25 × topic relevance`

   The 0–1 value is a heuristic ranking signal, not a validated probability. Position is handled during selection by choosing across topic regions.
8. **Selection:** rank candidates, remove overlaps after expansion, and select round-robin across topics before filling remaining slots. Persist the timestamp, text, title, topic, and score on the owning video.

## Analytics and limitations

Analytics queries real, owner-scoped video, transcript, summary, and key-moment rows. A semantic phrase is counted once per transcript in phrase summaries; aggregate totals are based on database records, not hardcoded values. Analytics is descriptive: it does not claim the keyphrase score or importance score is factual certainty.

YouTube URL processing and MCQ generation are unavailable because there is no corresponding supported backend pipeline. The interface should keep both features clearly unavailable. A separate content-abstraction/takeaway column would require a reviewed schema migration; the current implementation does not fabricate or persist such a field.
