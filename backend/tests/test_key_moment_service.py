from app.services.key_moment_service import (
    detect_key_moments,
    extract_keywords,
)


def test_keyword_extraction():
    segments = [
        {
            "start": 0,
            "end": 10,
            "text": "Python is important for machine learning.",
        },
        {
            "start": 10,
            "end": 20,
            "text": "Machine learning uses Python for data analysis.",
        },
    ]

    keywords = extract_keywords(segments)

    assert "python" in keywords
    assert "machine" in keywords


def test_key_moment_detection():
    segments = [
        {
            "start": 0,
            "end": 12,
            "text": "Today we will introduce the basic concept.",
        },
        {
            "start": 12,
            "end": 30,
            "text": (
                "The most important concept is that machine learning "
                "learns patterns from data."
            ),
        },
        {
            "start": 30,
            "end": 42,
            "text": "Now let us move to another example.",
        },
    ]

    moments = detect_key_moments(
        segments,
        threshold=0.30,
        max_moments=5,
    )

    assert len(moments) > 0

    moment = moments[0]

    assert moment.start_time >= 0
    assert moment.end_time > moment.start_time
    assert 0.0 <= moment.importance_score <= 1.0
    assert moment.text
def test_key_moment_topic_is_based_on_segment_content():
    segments = [
        {
            "start": 0.0,
            "end": 10.0,
            "text": (
                "Python programming is useful. "
                "Python programming helps developers."
            ),
        },
        {
            "start": 10.0,
            "end": 20.0,
            "text": (
                "Machine learning models learn from data. "
                "Machine learning can make predictions."
            ),
        },
    ]

    moments = detect_key_moments(
        segments,
        threshold=0.0,
        max_moments=10,
    )

    assert len(moments) == 2
    assert moments[0].topic == "Python"
    assert moments[1].topic == "Machine"

def test_topic_segmentation_groups_segments():
    from app.services.key_moment_service import segment_topics

    segments = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "Python programming is useful.",
        },
        {
            "start": 5.0,
            "end": 10.0,
            "text": "Python programming helps build applications.",
        },
        {
            "start": 10.0,
            "end": 15.0,
            "text": "FastAPI is useful for building APIs.",
        },
    ]

    topics = segment_topics(segments)

    assert topics
    assert all(topic["start"] < topic["end"] for topic in topics)
    assert all(topic["text"] for topic in topics)