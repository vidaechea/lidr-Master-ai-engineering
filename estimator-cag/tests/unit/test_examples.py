import json

from app.context.examples import (
    ESTIMATION_EXAMPLES,
    ESTIMATION_LABEL,
    EXAMPLE_HEADER_TEMPLATE,
    MEETING_SUMMARY_LABEL,
    ExampleFormat,
    format_examples_for_prompt,
    select_examples,
)


class TestEstimationExamples:
    def test_examples_list_has_at_least_two_items(self):
        assert len(ESTIMATION_EXAMPLES) >= 2

    def test_each_example_has_required_fields(self):
        for example in ESTIMATION_EXAMPLES:
            assert hasattr(example, "title")
            assert hasattr(example, "meeting_summary")
            assert hasattr(example, "breakdown")
            assert hasattr(example, "total_hours")
            assert hasattr(example, "total_cost")
            assert hasattr(example, "team")
            assert hasattr(example, "duration_weeks")
            assert hasattr(example, "estimation_markdown")

    def test_meeting_summary_is_non_empty_string(self):
        for example in ESTIMATION_EXAMPLES:
            assert isinstance(example.meeting_summary, str)
            assert len(example.meeting_summary.strip()) > 0

    def test_estimation_markdown_is_non_empty_string(self):
        for example in ESTIMATION_EXAMPLES:
            assert isinstance(example.estimation_markdown, str)
            assert len(example.estimation_markdown.strip()) > 0

    def test_returns_string(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.MARKDOWN)
        assert isinstance(result, str)

    def test_output_contains_all_example_markers(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.MARKDOWN)
        for i in range(1, len(ESTIMATION_EXAMPLES) + 1):
            assert EXAMPLE_HEADER_TEMPLATE.format(index=i) in result

    def test_output_contains_meeting_summary_label(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.MARKDOWN)
        assert MEETING_SUMMARY_LABEL in result

    def test_output_contains_estimation_label(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.MARKDOWN)
        assert ESTIMATION_LABEL in result

    def test_output_contains_each_meeting_summary_text(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.MARKDOWN)
        for example in ESTIMATION_EXAMPLES:
            fragment = example.meeting_summary[:40]
            assert fragment in result

    def test_output_is_not_empty(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.MARKDOWN)
        assert len(result.strip()) > 0


class TestSelectExamples:
    def test_returns_requested_number_of_examples(self):
        result = select_examples(2)
        assert len(result) == 2

    def test_returns_list_of_canonical_examples(self):
        result = select_examples(1)
        assert isinstance(result, list)
        assert hasattr(result[0], "title")

    def test_returns_all_when_n_equals_total(self):
        result = select_examples(len(ESTIMATION_EXAMPLES))
        assert len(result) == len(ESTIMATION_EXAMPLES)

    def test_returns_first_n_examples(self):
        result = select_examples(2)
        assert result == ESTIMATION_EXAMPLES[:2]


class TestFormatExamplesForPromptMarkdown:
    def test_markdown_format_returns_string(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.MARKDOWN)
        assert isinstance(result, str)

    def test_markdown_contains_example_headers(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.MARKDOWN)
        for i in range(1, len(ESTIMATION_EXAMPLES) + 1):
            assert EXAMPLE_HEADER_TEMPLATE.format(index=i) in result

    def test_markdown_contains_meeting_summary_label(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.MARKDOWN)
        assert MEETING_SUMMARY_LABEL in result

    def test_markdown_contains_estimation_label(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.MARKDOWN)
        assert ESTIMATION_LABEL in result


class TestFormatExamplesForPromptJson:
    def test_json_format_returns_valid_json(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.JSON)
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_json_has_one_entry_per_example(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.JSON)
        parsed = json.loads(result)
        assert len(parsed) == len(ESTIMATION_EXAMPLES)

    def test_json_entries_have_required_keys(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.JSON)
        parsed = json.loads(result)
        required_keys = {"index", "title", "meeting_summary", "breakdown", "total_hours", "total_cost_eur", "team", "duration_weeks"}
        for entry in parsed:
            assert required_keys.issubset(entry.keys())

    def test_json_breakdown_entries_have_required_keys(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.JSON)
        parsed = json.loads(result)
        for entry in parsed:
            for task in entry["breakdown"]:
                assert {"task", "hours", "cost_eur"}.issubset(task.keys())

    def test_json_total_hours_matches_source(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.JSON)
        parsed = json.loads(result)
        for entry, example in zip(parsed, ESTIMATION_EXAMPLES):
            assert entry["total_hours"] == example.total_hours

    def test_json_contains_each_meeting_summary_text(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.JSON)
        for example in ESTIMATION_EXAMPLES:
            assert example.meeting_summary[:40] in result


class TestFormatExamplesForPromptNarrative:
    def test_narrative_format_returns_string(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.NARRATIVE)
        assert isinstance(result, str)

    def test_narrative_is_not_empty(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.NARRATIVE)
        assert len(result.strip()) > 0

    def test_narrative_contains_each_title(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.NARRATIVE)
        for example in ESTIMATION_EXAMPLES:
            assert example.title in result

    def test_narrative_contains_each_meeting_summary_text(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.NARRATIVE)
        for example in ESTIMATION_EXAMPLES:
            assert example.meeting_summary[:40] in result

    def test_narrative_contains_total_hours_and_cost(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.NARRATIVE)
        for example in ESTIMATION_EXAMPLES:
            assert str(example.total_hours) in result
            assert str(example.total_cost) in result

    def test_narrative_has_one_block_per_example(self):
        result = format_examples_for_prompt(ESTIMATION_EXAMPLES, ExampleFormat.NARRATIVE)
        blocks = result.strip().split("\n\n")
        assert len(blocks) == len(ESTIMATION_EXAMPLES)