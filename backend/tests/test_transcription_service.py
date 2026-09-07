from types import SimpleNamespace

from app.services import transcription_service


def test_transcribe_audio_uses_mocked_lazy_model(monkeypatch, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    calls = []

    class FakeModel:
        def transcribe(self, path, **options):
            calls.append((path, options))
            return {
                "text": "Hello from ClipMind.",
                "language": "en",
                "segments": [{"id": 0, "start": 0.0, "end": 1.0, "text": "Hello"}],
            }

    monkeypatch.setattr(transcription_service, "load_whisper_model", lambda model_name: FakeModel())

    result = transcription_service.transcribe_audio(str(audio_path), language_hint="en")

    assert result.status == "completed"
    assert result.text == "Hello from ClipMind."
    assert result.language == "en"
    assert result.segments == [{"id": 0, "start": 0.0, "end": 1.0, "text": "Hello"}]
    assert calls == [(str(audio_path), {"language": "en"})]


def test_transcribe_audio_missing_audio_does_not_load_model(monkeypatch, tmp_path):
    monkeypatch.setattr(
        transcription_service,
        "load_whisper_model",
        lambda _model_name: (_ for _ in ()).throw(AssertionError("model should not load")),
    )

    result = transcription_service.transcribe_audio(str(tmp_path / "missing.wav"))

    assert result.status == "failed"
    assert result.error_code == "audio_not_found"


def test_transcribe_audio_model_failure_is_safe(monkeypatch, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    monkeypatch.setattr(
        transcription_service,
        "load_whisper_model",
        lambda _model_name: (_ for _ in ()).throw(RuntimeError("private model detail")),
    )

    result = transcription_service.transcribe_audio(str(audio_path))

    assert result.status == "failed"
    assert result.error_code == "model_load_failed"
    assert "private model detail" not in result.error_message


def test_transcribe_audio_failure_is_safe_and_uses_no_real_model(monkeypatch, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    fake_model = SimpleNamespace(
        transcribe=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("raw backend detail"))
    )
    monkeypatch.setattr(transcription_service, "load_whisper_model", lambda _model_name: fake_model)

    result = transcription_service.transcribe_audio(str(audio_path))

    assert result.status == "failed"
    assert result.error_code == "transcription_failed"
    assert "raw backend detail" not in result.error_message
