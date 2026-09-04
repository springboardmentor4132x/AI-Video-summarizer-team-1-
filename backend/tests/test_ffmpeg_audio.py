from pathlib import Path
from types import SimpleNamespace

from app.services import ffmpeg_service


def test_extract_audio_uses_safe_whisper_ready_ffmpeg_command(monkeypatch, tmp_path):
    video_path = tmp_path / "input.mp4"
    audio_path = tmp_path / "audio" / "output.wav"
    video_path.write_bytes(b"video")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ffmpeg_service.subprocess, "run", fake_run)

    result = ffmpeg_service.extract_audio(str(video_path), str(audio_path))

    assert result.status == "completed"
    assert result.audio_path == str(audio_path)
    assert result.error_code is None
    assert audio_path.parent.is_dir()
    assert calls == [
        (
            [
                "ffmpeg", "-nostdin", "-i", str(video_path), "-vn", "-ac", "1",
                "-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav", "-y", str(audio_path),
            ],
            {"capture_output": True, "text": True},
        )
    ]


def test_extract_audio_missing_input_removes_partial_output(tmp_path):
    audio_path = tmp_path / "partial.wav"
    audio_path.write_bytes(b"partial")

    result = ffmpeg_service.extract_audio(str(tmp_path / "missing.mp4"), str(audio_path))

    assert result.status == "failed"
    assert result.error_code == "input_not_found"
    assert not audio_path.exists()


def test_extract_audio_ffmpeg_failure_removes_partial_output(monkeypatch, tmp_path):
    video_path = tmp_path / "input.mp4"
    audio_path = tmp_path / "partial.wav"
    video_path.write_bytes(b"video")

    def fake_run(command, **_kwargs):
        Path(command[-1]).write_bytes(b"partial")
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(ffmpeg_service.subprocess, "run", fake_run)

    result = ffmpeg_service.extract_audio(str(video_path), str(audio_path))

    assert result.status == "failed"
    assert result.error_code == "ffmpeg_failed"
    assert not audio_path.exists()


def test_extract_audio_subprocess_start_failure_removes_partial_output(monkeypatch, tmp_path):
    video_path = tmp_path / "input.mp4"
    audio_path = tmp_path / "partial.wav"
    video_path.write_bytes(b"video")
    audio_path.write_bytes(b"partial")
    monkeypatch.setattr(ffmpeg_service.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError()))

    result = ffmpeg_service.extract_audio(str(video_path), str(audio_path))

    assert result.status == "failed"
    assert result.error_code == "ffmpeg_unavailable"
    assert not audio_path.exists()
