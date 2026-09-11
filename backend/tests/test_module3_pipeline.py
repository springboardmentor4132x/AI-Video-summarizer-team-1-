import numpy as np

from app.services.key_moment_service import (
    KeyMoment,
    calculate_similarities,
    cosine_similarity,
    detect_topics_semantic,
    remove_overlaps,
    segment_transcript,
)


def test_segment_transcript_preserves_timestamps_and_skips_invalid_segments():
    chunks = segment_transcript([
        {"start": 0, "end": 10, "text": "First sentence."},
        {"start": "bad", "end": 20, "text": "Ignored."},
        {"start": 10, "end": 20, "text": "Second sentence."},
    ])
    assert len(chunks) == 2
    assert chunks[0].start_time == 0
    assert chunks[0].end_time == 10
    assert chunks[0].source_segment_indexes == [0]
    assert chunks[1].start_time == 10
    assert chunks[1].end_time == 20
    assert chunks[1].source_segment_indexes == [2]


def test_cosine_similarity_handles_identical_unrelated_and_zero_vectors():
    assert cosine_similarity([1, 0], [1, 0]) == 1
    assert cosine_similarity([1, 0], [0, 1]) == 0
    assert cosine_similarity([0, 0], [1, 0]) == 0
    assert calculate_similarities(np.array([[1, 0], [1, 0], [0, 1]])) == [1.0, 0.0]


def test_semantic_similarity_drop_creates_topic_regions():
    chunks = segment_transcript([
        {"start": 0, "end": 10, "text": "Machine learning uses data."},
        {"start": 10, "end": 20, "text": "Machine learning finds patterns."},
        {"start": 20, "end": 30, "text": "Cooking recipes need ingredients."},
    ])
    regions = detect_topics_semantic(chunks, np.ones((3, 2)), [0.9, 0.2], boundary_threshold=0.45, min_region_chunks=1)
    assert len(regions) == 2
    assert regions[0].start_time == 0
    assert regions[1].start_time == 20


def test_semantic_segmentation_merges_isolated_weak_regions():
    chunks = segment_transcript([
        {"start": 0, "end": 10, "text": "Machine learning uses data."},
        {"start": 10, "end": 20, "text": "Machine learning finds patterns."},
        {"start": 20, "end": 30, "text": "Cooking recipes need ingredients."},
    ])
    regions = detect_topics_semantic(chunks, np.ones((3, 2)), [0.9, 0.2], boundary_threshold=0.45)
    assert len(regions) == 1
    assert regions[0].start_time == 0
    assert regions[0].end_time == 30


def test_topic_label_ignores_generic_narration_and_uses_local_content():
    chunks = segment_transcript([
        {"start": 0, "end": 10, "text": "Welcome to this course about machine learning."},
        {"start": 10, "end": 20, "text": "Number one is machine learning models."},
    ])
    regions = detect_topics_semantic(chunks, np.ones((2, 2)), [0.9], min_region_chunks=1)
    assert regions[0].label == "Machine"
    assert regions[0].start_time == 0
    assert regions[0].end_time == 20


def test_remove_overlaps_keeps_stronger_candidate_and_non_overlapping_candidates():
    candidates = [
        KeyMoment(10, 30, "A", "Topic", 0.82, "A"),
        KeyMoment(25, 45, "B", "Topic", 0.90, "B"),
        KeyMoment(60, 70, "C", "Other", 0.50, "C"),
    ]
    selected = remove_overlaps(candidates)
    assert [item.title for item in selected] == ["B", "C"]
