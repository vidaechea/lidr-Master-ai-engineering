"""Tests for example loading and formatting from prompt templates."""

import pytest

from app.prompts.loader import format_examples_for_prompt, get_examples
from app.schemas.estimation import ExampleFormat


class TestGetExamples:
    """Test loading examples from templates."""

    def test_get_examples_returns_list(self):
        examples = get_examples()
        assert isinstance(examples, list)

    def test_get_examples_returns_non_empty_list(self):
        examples = get_examples()
        assert len(examples) > 0

    def test_each_example_has_required_fields(self):
        examples = get_examples()
        for example in examples:
            assert hasattr(example, "title")
            assert hasattr(example, "meeting_summary")
            assert hasattr(example, "breakdown")
            assert hasattr(example, "total_hours")
            assert hasattr(example, "total_cost")
            assert hasattr(example, "team")
            assert hasattr(example, "duration_weeks")
            assert hasattr(example, "estimation_markdown")

    def test_examples_contain_valid_strings(self):
        examples = get_examples()
        for example in examples:
            assert isinstance(example.title, str) and len(example.title) > 0
            assert isinstance(example.meeting_summary, str) and len(example.meeting_summary) > 0
            assert isinstance(example.estimation_markdown, str) and len(example.estimation_markdown) > 0

    def test_examples_contain_valid_breakdown(self):
        examples = get_examples()
        for example in examples:
            assert isinstance(example.breakdown, list)
            assert len(example.breakdown) > 0
            for task, hours, cost in example.breakdown:
                assert isinstance(task, str) and len(task) > 0
                assert isinstance(hours, int) and hours > 0
                assert isinstance(cost, int) and cost > 0

    def test_examples_have_positive_totals(self):
        examples = get_examples()
        for example in examples:
            assert example.total_hours > 0
            assert example.total_cost > 0
            assert example.duration_weeks > 0

    def test_get_examples_caches_results(self):
        """Test that examples are cached after first load."""
        examples1 = get_examples()
        examples2 = get_examples()
        assert examples1 is examples2


class TestFormatExamplesForPrompt:
    """Test formatting examples for use in prompts."""

    @pytest.fixture
    def examples(self):
        """Provide examples for testing."""
        return get_examples()

    def test_markdown_format_returns_string(self, examples):
        result = format_examples_for_prompt(examples, ExampleFormat.MARKDOWN)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_markdown_format_contains_example_headers(self, examples):
        result = format_examples_for_prompt(examples, ExampleFormat.MARKDOWN)
        for i in range(1, len(examples) + 1):
            assert f"--- Example {i} ---" in result

    def test_markdown_format_contains_meeting_summary_label(self, examples):
        result = format_examples_for_prompt(examples, ExampleFormat.MARKDOWN)
        assert "Meeting summary:" in result

    def test_markdown_format_contains_estimation_label(self, examples):
        result = format_examples_for_prompt(examples, ExampleFormat.MARKDOWN)
        assert "Generated estimation:" in result

    def test_json_format_returns_valid_json(self, examples):
        import json

        result = format_examples_for_prompt(examples, ExampleFormat.JSON)
        assert isinstance(result, str)
        data = json.loads(result)  # Should not raise
        assert isinstance(data, list)
        assert len(data) == len(examples)

    def test_json_format_contains_required_fields(self, examples):
        import json

        result = format_examples_for_prompt(examples, ExampleFormat.JSON)
        data = json.loads(result)
        for item in data:
            assert "index" in item
            assert "title" in item
            assert "meeting_summary" in item
            assert "breakdown" in item
            assert "total_hours" in item
            assert "total_cost_eur" in item
            assert "team" in item
            assert "duration_weeks" in item

    def test_narrative_format_returns_string(self, examples):
        result = format_examples_for_prompt(examples, ExampleFormat.NARRATIVE)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_narrative_format_contains_example_indicators(self, examples):
        result = format_examples_for_prompt(examples, ExampleFormat.NARRATIVE)
        for i in range(1, len(examples) + 1):
            assert f"Example {i}" in result

    def test_invalid_format_raises_error(self, examples):
        with pytest.raises(ValueError, match="Unsupported example format"):
            format_examples_for_prompt(examples, "invalid_format")  # type: ignore

    def test_format_with_single_example(self, examples):
        single = examples[:1]
        result = format_examples_for_prompt(single, ExampleFormat.MARKDOWN)
        assert "--- Example 1 ---" in result
        assert "--- Example 2 ---" not in result

    def test_format_with_subset_of_examples(self, examples):
        if len(examples) >= 2:
            subset = examples[:2]
            result = format_examples_for_prompt(subset, ExampleFormat.MARKDOWN)
            assert "--- Example 1 ---" in result
            assert "--- Example 2 ---" in result
            if len(examples) > 2:
                assert "--- Example 3 ---" not in result
