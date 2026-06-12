from pathlib import Path

import pytest

from app.domain.schemas.estimation import EstimationRequest, _load_example_transcription

_FIXTURES_DIR = Path(__file__).parent.parent.parent / "app" / "foundation" / "fixtures"


class TestLoadExampleTranscription:
    def test_returns_none_when_fixture_is_none(self):
        assert _load_example_transcription(None) is None

    def test_returns_none_when_fixture_is_empty_string(self):
        assert _load_example_transcription("") is None

    def test_returns_string_for_short_fixture(self):
        result = _load_example_transcription("short", _FIXTURES_DIR)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_string_for_long_fixture(self):
        result = _load_example_transcription("long", _FIXTURES_DIR)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_long_fixture_is_longer_than_short(self):
        short = _load_example_transcription("short", _FIXTURES_DIR)
        long = _load_example_transcription("long", _FIXTURES_DIR)
        assert len(long) > len(short)

    def test_raises_if_fixture_file_does_not_exist(self):
        with pytest.raises(FileNotFoundError):
            _load_example_transcription("nonexistent", _FIXTURES_DIR)


class TestEstimationRequestSwaggerExample:
    def _get_example(self) -> dict:
        return EstimationRequest.model_config["json_schema_extra"]["example"]

    def test_example_contains_required_non_transcription_fields(self):
        example = self._get_example()
        assert "evaluate" in example
        assert "model" in example
        assert "temperature" in example
        assert "max_output_tokens" in example
        assert "pre_call" in example

    def test_transcription_absent_or_non_empty(self):
        example = self._get_example()
        if "transcription" in example:
            assert isinstance(example["transcription"], str)
            assert len(example["transcription"]) > 0

    def test_example_temperature_within_valid_range(self):
        example = self._get_example()
        assert 0.0 <= example["temperature"] <= 2.0

    def test_example_model_is_valid_literal(self):
        import typing
        from app.config import LLMModel
        valid_models = typing.get_args(LLMModel)
        example_model = self._get_example().get("model")
        assert example_model is not None
        assert example_model in valid_models

