from types import SimpleNamespace

from app.services import summarization_service
from app.models.transcript import Transcript, TranscriptStatus


def test_two_video_summaries_never_include_the_other_transcripts(monkeypatch):
    def summarize(text, **_kwargs):
        if "Ganga" in text:
            return summarization_service.SummaryResult(
                "Indian river systems support varied regions.",
                "The Ganga and Brahmaputra are major northern rivers. The Godavari is a key peninsular river.",
            )
        return summarization_service.SummaryResult(
            "The video introduces a DevOps learning path.",
            "The DevOps roadmap covers Linux, networking, containers, CI pipelines, and monitoring.",
        )

    monkeypatch.setattr(summarization_service, "_summarize_with_hf", summarize)
    transcript_a = Transcript(
        id=101,
        video_id=201,
        status=TranscriptStatus.COMPLETED,
        text=(
            "The Ganga flows across northern India and supports agriculture. "
            "The Brahmaputra enters India through Arunachal Pradesh. "
            "The Godavari is an important peninsular river."
        ),
    )
    transcript_b = Transcript(
        id=102,
        video_id=202,
        status=TranscriptStatus.COMPLETED,
        text=(
            "The DevOps roadmap begins with Linux and networking. "
            "Teams use containers and CI pipelines to deploy applications. "
            "Monitoring helps teams maintain reliable services."
        ),
    )

    summary_a = summarization_service.summarize_transcript(transcript_a)
    summary_b = summarization_service.summarize_transcript(transcript_b)

    assert "Ganga" in summary_a.detailed_summary
    assert "DevOps" not in summary_a.short_summary + summary_a.detailed_summary
    assert "Brahmaputra" not in summary_b.short_summary + summary_b.detailed_summary
    assert "Linux" in summary_b.detailed_summary


class FakeTokenizer:
    def encode(self, text, add_special_tokens=False):
        return text.split()


class FakeModel:
    config = SimpleNamespace(model_type="bart", max_position_embeddings=1024)


def test_generation_uses_bart_length_parameters_without_truncation():
    import torch

    class Tokenizer(FakeTokenizer):
        def __call__(self, text, *, return_tensors, truncation):
            assert return_tensors == "pt"
            assert truncation is False
            return {"input_ids": torch.tensor([[0, 1, 2]])}

        def decode(self, _tokens, *, skip_special_tokens):
            assert skip_special_tokens
            return "A grounded summary."

    class Model(FakeModel):
        def generate(self, **kwargs):
            self.generation_kwargs = kwargs
            return torch.tensor([[0, 2]])

    model = Model()
    result = summarization_service._generate(
        "A short source sentence.", Tokenizer(), model,
        max_length=120, min_length=32, max_input_tokens=100,
    )
    assert result == "A grounded summary."
    assert model.generation_kwargs["max_length"] == 120
    assert model.generation_kwargs["min_length"] == 32
    assert model.generation_kwargs["num_beams"] == 4
    assert model.generation_kwargs["length_penalty"] == 2.0
    assert model.generation_kwargs["no_repeat_ngram_size"] == 3
    assert model.generation_kwargs["early_stopping"] is True
    assert model.generation_kwargs["encoder_no_repeat_ngram_size"] == 3
    assert "max_new_tokens" not in model.generation_kwargs


def test_single_chunk_model_generates_abstractive_detailed_and_short_summaries(monkeypatch):
    source = (
        "A lecture opens with a discussion of river origins and watershed geography. "
        "It compares tributaries and the communities that depend on seasonal flow."
    )
    detailed = "The lecture connects river formation, tributary networks, and human use of water.\n\nIt explains how these systems shape communities."
    short = "River systems shape geography and daily life through linked waterways.\n\nThe video also explains why watersheds matter to communities."
    monkeypatch.setattr(summarization_service, "_load_model", lambda _name: (FakeTokenizer(), FakeModel()))
    generated = iter(["The section explains rivers, watersheds, and community dependence.", detailed, short])
    seen_inputs = []

    def generate(text, *_args, **_kwargs):
        seen_inputs.append(text)
        return next(generated)

    monkeypatch.setattr(summarization_service, "_generate", generate)

    result = summarization_service._summarize_with_hf(source)

    assert result is not None
    assert result.detailed_summary == detailed
    assert result.short_summary == short
    assert result.detailed_summary not in source
    assert len(seen_inputs) == 3
    assert seen_inputs[0] == source
    assert seen_inputs[1] == "The section explains rivers, watersheds, and community dependence."


def test_long_transcript_summarizes_each_chunk_then_synthesizes(monkeypatch):
    source = " ".join(
        f"Topic {index} explains a distinct concept and its practical relationship."
        for index in range(240)
    )
    tokenizer = FakeTokenizer()
    model = FakeModel()
    chunk_limit = min(
        512,
        summarization_service._model_input_limit(tokenizer, model) - 2,
    )
    chunks = summarization_service._chunk_text(
        source,
        tokenizer=tokenizer,
        max_tokens=chunk_limit,
    )
    assert len(chunks) > 1
    assert all(
        len(tokenizer.encode(chunk)) <= summarization_service._MAX_INPUT_TOKENS
        for chunk in chunks
    )

    monkeypatch.setattr(summarization_service, "_load_model", lambda _name: (tokenizer, model))
    detailed = "The lesson connects its distinct concepts with practical examples and explains why the relationships matter. " * 45
    short = "The video explains its central subject and connects major ideas with useful examples. " * 22
    outputs = iter(
        [f"Abstracted chunk {index} overview." for index in range(len(chunks))]
        + [detailed, short]
    )
    seen_inputs = []

    def generate(text, *_args, **_kwargs):
        seen_inputs.append(text)
        return next(outputs)

    monkeypatch.setattr(summarization_service, "_generate", generate)

    result = summarization_service._summarize_with_hf(source)

    assert result is not None
    assert len(seen_inputs) == len(chunks) + 2
    assert "Abstracted chunk 0 overview." in seen_inputs[-2]
    assert "Abstracted chunk 1 overview." in seen_inputs[-2]
    assert result.detailed_summary not in source
    assert len(result.short_summary.split()) > 10
    assert len(result.detailed_summary.split()) > len(result.short_summary.split())


def test_model_load_failure_is_reported_instead_of_returning_extracts(monkeypatch):
    monkeypatch.setattr(
        summarization_service,
        "_load_model",
        lambda _name: (_ for _ in ()).throw(OSError("model files unavailable")),
    )
    import pytest

    with pytest.raises(summarization_service.SummarizationError):
        summarization_service._summarize_with_hf("A source transcript with several concepts.")


def test_short_transcript_is_synthesized_without_length_filler(monkeypatch):
    source = "A short lesson compares the Ganga and Godavari river systems."
    expected = summarization_service.SummaryResult(
        "The lesson briefly compares two Indian river systems.",
        "The short lesson contrasts the Ganga and Godavari, focusing on their role as distinct river systems.",
    )
    monkeypatch.setattr(summarization_service, "_summarize_with_hf", lambda _text, **_kwargs: expected)
    result = summarization_service.summarize_transcript(
        Transcript(id=1, video_id=1, status=TranscriptStatus.COMPLETED, text=source)
    )
    assert result == expected
    assert result.short_summary not in source
    assert result.detailed_summary not in source
    assert len(result.detailed_summary.split()) < 50


def test_long_summary_prompts_request_grounded_paragraph_synthesis(monkeypatch):
    source = " ".join(f"Section {i} describes a different part of the lesson." for i in range(180))
    tokenizer = FakeTokenizer()
    monkeypatch.setattr(summarization_service, "_load_model", lambda _name: (tokenizer, FakeModel()))
    prompts: list[str] = []

    def generate(_text, _tokenizer, _model, *, instruction, max_length, min_length, **_kwargs):
        prompts.append(instruction)
        if "coherent detailed explanation" in instruction:
            assert max_length > min_length
            return "\n\n".join(
                f"Paragraph {index} explains the lesson's separate ideas, related examples, and how each one supports the larger subject. " * 5
                for index in range(1, 10)
            )
        if "concise but informative overview" in instruction:
            assert max_length > min_length
            return "\n\n".join(
                f"Paragraph {index} introduces a major idea and explains its relation to the video's central subject. " * 3
                for index in range(1, 6)
            )
        return "The section covers distinct grounded ideas and examples."

    monkeypatch.setattr(summarization_service, "_generate", generate)
    result = summarization_service._summarize_with_hf(source)
    assert result.short_summary.count("\n\n") >= 4
    assert result.detailed_summary.count("\n\n") >= 8
    assert all(
        any(term in prompt.lower() for term in ("use only", "do not add", "do not invent"))
        for prompt in prompts
    )


def test_quality_gate_rejects_short_or_extractively_copied_outputs():
    import pytest

    source = " ".join(
        f"Section {index} explains a separate concept and how that concept supports the overall lesson."
        for index in range(30)
    )
    with pytest.raises(summarization_service.SummarizationError, match="undersized"):
        summarization_service._validate_summary_quality(source, "One short line.", "A few copied words.")

    copied = " ".join(
        f"Section {index} explains a separate concept and how that concept supports the overall lesson."
        for index in range(20)
    )
    long_summary = " ".join(
        f"Section {index} explains a separate concept and how that concept supports the overall lesson."
        for index in range(11)
    )
    with pytest.raises(summarization_service.SummarizationError, match="extractive"):
        summarization_service._validate_summary_quality(
            source,
            "The overview connects the video's central themes with examples and practical implications. " * 6,
            long_summary,
        )


def test_t5_prompt_requests_grounded_abstractive_summary_and_respects_context():
    t5 = SimpleNamespace(
        config=SimpleNamespace(model_type="t5", max_position_embeddings=512)
    )
    tokenizer = SimpleNamespace(model_max_length=512)

    prompt = summarization_service._format_model_input(
        "Source facts about several topics.",
        t5,
        "Synthesize the lecture in your own words.",
    )

    assert "Synthesize the lecture in your own words." in prompt
    assert "Source facts about several topics." in prompt
    assert summarization_service._model_input_limit(tokenizer, t5) == 510


def test_default_model_is_bart_large_cnn():
    assert summarization_service._DEFAULT_MODEL == "facebook/bart-large-cnn"


def test_model_and_tokenizer_initialize_lazily_as_a_cached_pair(monkeypatch):
    import transformers

    calls = []
    model = FakeModel()
    model.to = lambda device: calls.append(("device", device)) or model
    model.eval = lambda: calls.append(("eval",)) or model

    class TokenizerLoader:
        @staticmethod
        def from_pretrained(name):
            calls.append(("tokenizer", name))
            return FakeTokenizer()

    class ModelLoader:
        @staticmethod
        def from_pretrained(name):
            calls.append(("model", name))
            return model

    monkeypatch.setattr(transformers, "AutoTokenizer", TokenizerLoader)
    monkeypatch.setattr(transformers, "AutoModelForSeq2SeqLM", ModelLoader)
    summarization_service._load_model.cache_clear()
    try:
        first = summarization_service._load_model("facebook/bart-large-cnn")
        second = summarization_service._load_model("facebook/bart-large-cnn")
        assert first is second
        assert calls[:2] == [
            ("tokenizer", "facebook/bart-large-cnn"),
            ("model", "facebook/bart-large-cnn"),
        ]
        assert ("device", "cpu") in calls
        assert ("eval",) in calls
    finally:
        summarization_service._load_model.cache_clear()


def test_generation_loads_the_configured_bart_model(monkeypatch):
    model_names = []
    monkeypatch.setattr(
        summarization_service,
        "_load_model",
        lambda name: (model_names.append(name) or (FakeTokenizer(), FakeModel())),
    )
    generated = iter([
        "A section note connecting related ideas.",
        "The lesson relates several ideas through a practical example.",
        "The video explains its central subject and main takeaway.",
    ])
    monkeypatch.setattr(summarization_service, "_generate", lambda *_args, **_kwargs: next(generated))
    summarization_service._summarize_with_hf("A short lesson covers a distinct subject and its example.")
    assert model_names == ["facebook/bart-large-cnn"]


def test_chunking_preserves_order_and_content_while_respecting_token_limit():
    source = "First coherent point explains the opening idea. Second point develops another concept. " + (
        "A very long explanation " * 80
    )
    tokenizer = FakeTokenizer()
    chunks = summarization_service._chunk_text(source, tokenizer=tokenizer, max_tokens=12)
    assert len(chunks) > 2
    assert all(len(tokenizer.encode(chunk)) <= 12 for chunk in chunks)
    assert " ".join(" ".join(chunks).split()) == " ".join(source.split())
    assert "First coherent point" in chunks[0]
    assert "Second point" in " ".join(chunks)


def test_chunk_summary_uses_single_chunk_pass_and_final_quality_gate_rejects_copy(monkeypatch):
    source = "The river begins in the northern mountains and supports farming across the valley."
    copied = "The river begins in the northern mountains and supports farming across the valley."
    calls = []

    def generate(_text, _tokenizer, _model, **kwargs):
        calls.append(kwargs["instruction"])
        return copied

    monkeypatch.setattr(summarization_service, "_generate", generate)
    selected = summarization_service._summarize_chunk(source, FakeTokenizer(), FakeModel(), 512)
    assert len(calls) == 1
    assert "specific semantic notes" in calls[0]
    assert selected == copied
    import pytest
    with pytest.raises(summarization_service.SummarizationError, match="extractive"):
        summarization_service._validate_summary_quality(
            source * 15,
            "The lesson presents a central idea and explains its important implications. " * 6,
            (copied + " ") * 15,
        )


def test_quality_metrics_report_lengths_compression_copying_and_topic_coverage():
    source = "Kubernetes deploys containers. Monitoring tracks service reliability."
    metrics = summarization_service._quality_metrics(
        source,
        "The video explains deployment and service health.",
        "Container orchestration supports reliable software delivery, while monitoring helps teams detect service problems.",
    )
    assert metrics["transcript_words"] == len(source.split())
    assert metrics["short_words"] > 0
    assert metrics["detailed_words"] > metrics["short_words"]
    assert 0 <= metrics["topic_coverage"] <= 1
    assert metrics["longest_shared_phrase_words"] < 10
    assert not metrics["extractive"]


def test_oversized_generation_input_fails_instead_of_silently_dropping_tail():
    """The generation helper must never return only the first piece of an oversized input."""
    import pytest

    source = " ".join(f"Sentence {i} contains distinct information about topic {i}." for i in range(400))
    tokenizer = FakeTokenizer()
    fake_model = SimpleNamespace(config=SimpleNamespace(model_type="t5", max_position_embeddings=512))

    with pytest.raises(summarization_service.SummarizationError, match="exceeds the safe model limit"):
        summarization_service._safe_format_and_chunk(
            source, tokenizer, fake_model, "Test instruction",
            max_input_tokens=summarization_service._MAX_INPUT_TOKENS,
        )


def test_long_input_is_segmented_into_complete_token_bounded_chunks():
    source = " ".join(f"Point {i} explains a concept." for i in range(500))
    tokenizer = FakeTokenizer()
    chunks = summarization_service._chunk_text(source, tokenizer=tokenizer, max_tokens=600)
    assert len(chunks) > 1
    assert all(len(tokenizer.encode(chunk)) + 2 <= 600 for chunk in chunks)
    assert " ".join(" ".join(chunks).split()) == " ".join(source.split())


def test_500_token_transcript_generates_summary(monkeypatch):
    """Test summarization of a 500+ token transcript."""
    # Generate a transcript with approximately 500+ tokens
    source = " ".join(
        f"Section {i} discusses concept {i} with detailed explanation and examples. "
        for i in range(150)
    )
    
    tokenizer = FakeTokenizer()
    fake_model = FakeModel()
    
    # Verify we have 500+ tokens
    assert len(tokenizer.encode(source)) > 500
    
    monkeypatch.setattr(summarization_service, "_load_model", lambda _: (tokenizer, fake_model))
    
    detailed = "The lecture covers comprehensive topics with systematic explanations and detailed analysis. " * 35
    short = "The video explains multiple interconnected concepts with practical examples and implications. " * 15
    
    def mock_generate(text, *_args, **_kwargs):
        # Return appropriate response based on what the function is requesting
        if "coherent detailed" in _kwargs.get("instruction", ""):
            return detailed
        if "concise but" in _kwargs.get("instruction", ""):
            return short
        # For chunk summaries
        return "Section abstract with key information."
    
    monkeypatch.setattr(summarization_service, "_generate", mock_generate)
    
    result = summarization_service._summarize_with_hf(source)
    assert result is not None
    assert len(result.short_summary) > 0
    assert len(result.detailed_summary) > len(result.short_summary)


def test_650_token_transcript_with_hierarchical_reduction(monkeypatch):
    """Test that hierarchical reduction works correctly for 650+ token transcripts."""
    # Generate a large transcript
    source = " ".join(
        f"Topic {i} describes a concept with multiple aspects and examples explained in detail. "
        for i in range(200)
    )
    
    tokenizer = FakeTokenizer()
    fake_model = FakeModel()
    
    # Verify we have 650+ tokens
    source_tokens = len(tokenizer.encode(source))
    assert source_tokens > 650
    
    monkeypatch.setattr(summarization_service, "_load_model", lambda _: (tokenizer, fake_model))
    
    # Track calls to _generate to ensure reduction happens
    generate_calls = []
    
    def mock_generate(text, tokenizer, model, **kwargs):
        generate_calls.append({
            "text_tokens": len(tokenizer.encode(text)),
            "instruction": kwargs.get("instruction", ""),
        })
        if "coherent detailed" in kwargs.get("instruction", ""):
            return "The comprehensive summary explains all major topics with relationships and analysis. " * 35
        if "concise but" in kwargs.get("instruction", ""):
            return "The video covers key concepts and their interconnections with practical implications. " * 15
        if "Consolidate" in kwargs.get("instruction", ""):
            return "Consolidated notes from multiple sections summarizing important information. " * 8
        return "Abstract summary of section with key insights."
    
    monkeypatch.setattr(summarization_service, "_generate", mock_generate)
    
    result = summarization_service._summarize_with_hf(source)
    
    # Should have multiple _generate calls: chunk summaries + reduction + detailed + short
    assert len(generate_calls) > 4
    # All calls should respect the token limit
    assert all(call["text_tokens"] <= summarization_service._MAX_INPUT_TOKENS for call in generate_calls)
    assert result is not None


def test_1000_plus_token_transcript_completes_successfully(monkeypatch):
    """Test summarization of a very long transcript (1000+ tokens)."""
    # Generate a very long transcript
    source = " ".join(
        f"Paragraph {i} contains multiple sentences explaining different aspects of a topic. "
        f"It includes examples, context, and relationships to other concepts. "
        for i in range(300)
    )
    
    tokenizer = FakeTokenizer()
    fake_model = FakeModel()
    
    # Verify we have 1000+ tokens
    source_tokens = len(tokenizer.encode(source))
    assert source_tokens > 1000
    
    monkeypatch.setattr(summarization_service, "_load_model", lambda _: (tokenizer, fake_model))
    
    generation_count = [0]
    
    def mock_generate(text, tokenizer, model, **kwargs):
        generation_count[0] += 1
        # Verify every call respects token limit
        formatted_tokens = len(tokenizer.encode(text))
        assert formatted_tokens <= summarization_service._MAX_INPUT_TOKENS, \
            f"Call {generation_count[0]}: {formatted_tokens} tokens > limit {summarization_service._MAX_INPUT_TOKENS}"
        
        if "coherent detailed" in kwargs.get("instruction", ""):
            return "Detailed explanation of all topics with relationships and implications. " * 40
        if "concise but" in kwargs.get("instruction", ""):
            return "Brief overview of main topics and their interconnections. " * 15
        if "Consolidate" in kwargs.get("instruction", ""):
            return "Combined summary of major topics. " * 8
        return "Topic summary and abstract."
    
    monkeypatch.setattr(summarization_service, "_generate", mock_generate)
    
    result = summarization_service._summarize_with_hf(source)
    
    assert result is not None
    assert len(result.short_summary) > 0
    assert len(result.detailed_summary) > 0
    assert generation_count[0] > 0  # Multiple generations should have occurred


def test_tokenizer_chunking_preserves_sentence_boundaries_and_all_content():
    """Long inputs split on sentences without dropping later sections."""
    source = (
        "First sentence ends here. "
        "Second sentence contains important information. "
        "Third sentence is the last one. "
    ) * 100
    
    tokenizer = FakeTokenizer()
    chunks = summarization_service._chunk_text(source, tokenizer=tokenizer, max_tokens=500)
    assert len(chunks) > 1
    assert all(len(tokenizer.encode(chunk)) + 2 <= 500 for chunk in chunks)
    assert " ".join(" ".join(chunks).split()) == " ".join(source.split())
    assert all(chunk.endswith(".") for chunk in chunks[:-1])
