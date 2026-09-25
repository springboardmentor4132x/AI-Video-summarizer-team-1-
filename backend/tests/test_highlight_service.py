import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import highlight_service
from app.services.key_moment_service import detect_key_moments


def test_extract_highlight_success_uses_safe_ffmpeg_command(monkeypatch, tmp_path):
    video_path = tmp_path / "input.mp4"
    output_path = tmp_path / "highlights" / "clip.mp4"
    video_path.write_bytes(b"video-data")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(highlight_service.subprocess, "run", fake_run)

    result = highlight_service.extract_highlight(
        video_path=str(video_path),
        start_time=5.0,
        end_time=15.0,
        output_path=str(output_path),
    )

    assert result.status == "completed"
    assert result.highlight_path == str(output_path)
    assert result.error_code is None
    assert output_path.parent.is_dir()
    assert len(calls) == 1

    command, kwargs = calls[0]
    assert command == [
        "ffmpeg",
        "-nostdin",
        "-ss",
        "5.0",
        "-i",
        str(video_path),
        "-t",
        "10.0",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-y",
        str(output_path),
    ]
    assert kwargs.get("shell") is not True
    assert kwargs == {"capture_output": True, "text": True}


def test_extract_highlight_missing_input_removes_partial_output(tmp_path):
    output_path = tmp_path / "partial.mp4"
    output_path.write_bytes(b"partial-data")

    result = highlight_service.extract_highlight(
        video_path=str(tmp_path / "missing.mp4"),
        start_time=0.0,
        end_time=10.0,
        output_path=str(output_path),
    )

    assert result.status == "failed"
    assert result.error_code == "input_not_found"
    assert not output_path.exists()


@pytest.mark.parametrize(
    "start_time, end_time",
    [
        (-1.0, 10.0),
        (10.0, 5.0),
        (5.0, 5.0),
        (float("nan"), 10.0),
        (0.0, float("inf")),
        ("invalid", 10.0),
    ],
)
def test_extract_highlight_invalid_timestamps(tmp_path, start_time, end_time):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"video-data")
    output_path = tmp_path / "partial.mp4"
    output_path.write_bytes(b"partial-data")

    result = highlight_service.extract_highlight(
        video_path=str(video_path),
        start_time=start_time,
        end_time=end_time,
        output_path=str(output_path),
    )

    assert result.status == "failed"
    assert result.error_code == "invalid_timestamps"
    assert not output_path.exists()


def test_extract_highlight_ffmpeg_failure_removes_partial_output(monkeypatch, tmp_path):
    video_path = tmp_path / "input.mp4"
    output_path = tmp_path / "partial.mp4"
    video_path.write_bytes(b"video-data")

    def fake_run(command, **_kwargs):
        Path(command[-1]).write_bytes(b"partial-corrupted")
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(highlight_service.subprocess, "run", fake_run)

    result = highlight_service.extract_highlight(
        video_path=str(video_path),
        start_time=2.0,
        end_time=8.0,
        output_path=str(output_path),
    )

    assert result.status == "failed"
    assert result.error_code == "ffmpeg_failed"
    assert not output_path.exists()


def test_extract_highlight_subprocess_error_removes_partial_output(monkeypatch, tmp_path):
    video_path = tmp_path / "input.mp4"
    output_path = tmp_path / "partial.mp4"
    video_path.write_bytes(b"video-data")
    output_path.write_bytes(b"partial-data")

    monkeypatch.setattr(
        highlight_service.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("ffmpeg not found")),
    )

    result = highlight_service.extract_highlight(
        video_path=str(video_path),
        start_time=1.0,
        end_time=5.0,
        output_path=str(output_path),
    )

    assert result.status == "failed"
    assert result.error_code == "ffmpeg_unavailable"
    assert not output_path.exists()


def test_extract_highlights_from_detected_key_moments_integration(monkeypatch, tmp_path):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"video-data")
    out_dir = tmp_path / "extracted_highlights"

    segments = [
        {
            "start": 0.0,
            "end": 10.0,
            "text": "Introduction to Python programming language.",
        },
        {
            "start": 10.0,
            "end": 25.0,
            "text": "The most important concept is machine learning with Python.",
        },
        {
            "start": 25.0,
            "end": 40.0,
            "text": "FastAPI enables high performance web APIs.",
        },
    ]

    moments = detect_key_moments(segments, threshold=0.0, max_moments=5)
    assert len(moments) > 0

    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(highlight_service.subprocess, "run", fake_run)

    results = highlight_service.extract_highlights_for_key_moments(
        video_path=str(video_path),
        moments=moments,
        output_dir=str(out_dir),
    )

    assert len(results) == len(moments)
    assert all(r.status == "completed" for r in results)
    assert len(commands) == len(moments)

    for moment, cmd in zip(moments, commands):
        assert str(moment.start_time) in cmd
        duration = str(moment.end_time - moment.start_time)
        assert duration in cmd


def test_extract_highlights_preserves_result_for_missing_timestamps(
    monkeypatch,
    tmp_path,
):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"video-data")
    moments = [
        SimpleNamespace(start_time=0.0, end_time=5.0),
        SimpleNamespace(start_time=None, end_time=None),
        SimpleNamespace(start_time=10.0, end_time=15.0),
    ]

    monkeypatch.setattr(
        highlight_service,
        "extract_highlight",
        lambda **_kwargs: highlight_service.HighlightExtractionResult(
            status="completed",
            highlight_path="generated.mp4",
        ),
    )

    results = highlight_service.extract_highlights_for_key_moments(
        video_path=video_path,
        moments=moments,
        output_dir=tmp_path / "highlights",
    )

    assert len(results) == len(moments)
    assert results[0].status == "completed"
    assert results[1].status == "failed"
    assert results[1].error_code == "invalid_timestamps"
    assert results[2].status == "completed"
