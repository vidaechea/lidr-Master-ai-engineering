from app.context.examples import (
    ESTIMATION_EXAMPLES,
    ESTIMATION_LABEL,
    EXAMPLE_HEADER_TEMPLATE,
    MEETING_SUMMARY_LABEL,
)


class TestEstimationExamples:
    def test_examples_list_has_at_least_two_items(self):
        assert len(ESTIMATION_EXAMPLES) >= 2

    def test_each_example_has_required_fields(self):
        for example in ESTIMATION_EXAMPLES:
            assert hasattr(example, "meeting_summary")
            assert hasattr(example, "estimation")

    def test_meeting_summary_is_non_empty_string(self):
        for example in ESTIMATION_EXAMPLES:
            assert isinstance(example.meeting_summary, str)
            assert len(example.meeting_summary.strip()) > 0

    def test_estimation_is_non_empty_string(self):
        for example in ESTIMATION_EXAMPLES:
            assert isinstance(example.estimation, str)
            assert len(example.estimation.strip()) > 0

    def test_returns_string(self):
        result = ESTIMATION_EXAMPLES.as_context()
        assert isinstance(result, str)

    def test_output_contains_all_example_markers(self):
        result = ESTIMATION_EXAMPLES.as_context()
        for i in range(1, len(ESTIMATION_EXAMPLES) + 1):
            assert EXAMPLE_HEADER_TEMPLATE.format(index=i) in result

    def test_output_contains_meeting_summary_label(self):
        result = ESTIMATION_EXAMPLES.as_context()
        assert MEETING_SUMMARY_LABEL in result

    def test_output_contains_estimation_label(self):
        result = ESTIMATION_EXAMPLES.as_context()
        assert ESTIMATION_LABEL in result

    def test_output_contains_each_meeting_summary_text(self):
        result = ESTIMATION_EXAMPLES.as_context()
        for example in ESTIMATION_EXAMPLES:
            fragment = example.meeting_summary[:40]
            assert fragment in result

    def test_output_is_not_empty(self):
        result = ESTIMATION_EXAMPLES.as_context()
        assert len(result.strip()) > 0