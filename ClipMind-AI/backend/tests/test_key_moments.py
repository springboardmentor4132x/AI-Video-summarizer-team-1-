from types import SimpleNamespace

from app.services.key_moments import detect_key_moments


def test_key_moments_detect_lexical_topic_boundaries() -> None:
    transcript = SimpleNamespace(
        video_id="00000000-0000-0000-0000-000000000001",
        segments=[
            {"start_time": 0, "end_time": 4, "text": "Planning starts with a clear goal and audience."},
            {"start_time": 4, "end_time": 8, "text": "The planning process identifies the main problem."},
            {"start_time": 8, "end_time": 12, "text": "Now let us review deployment monitoring and results."},
            {"start_time": 12, "end_time": 16, "text": "Deployment results improve when monitoring is consistent."},
            {"start_time": 16, "end_time": 20, "text": "Planning also measures audience needs and outcomes."},
            {"start_time": 20, "end_time": 24, "text": "The planning review confirms the main objectives."},
            {"start_time": 24, "end_time": 28, "text": "Now deployment monitoring checks reliability and results."},
            {"start_time": 28, "end_time": 32, "text": "Deployment results are recorded for the next review."},
        ],
    )

    moments = detect_key_moments(transcript)

    assert len(moments) == 2
    assert moments[0].topic
    assert moments[1].topic
    assert moments[0].end_time <= moments[1].start_time
    assert all(0 <= moment.importance_score <= 1 for moment in moments)