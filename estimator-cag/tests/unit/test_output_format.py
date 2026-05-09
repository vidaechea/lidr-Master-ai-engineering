import pytest

from app.schemas.estimation import ExampleFormat
from app.schemas.estimation import OutputFormat


class TestOutputFormatToExampleFormat:
    def test_phases_table_maps_to_markdown(self):
        assert OutputFormat.PHASES_TABLE.to_example_format() == ExampleFormat.MARKDOWN

    def test_line_items_maps_to_markdown(self):
        assert OutputFormat.LINE_ITEMS.to_example_format() == ExampleFormat.MARKDOWN

    def test_narrative_maps_to_narrative(self):
        assert OutputFormat.NARRATIVE.to_example_format() == ExampleFormat.NARRATIVE

    def test_legacy_markdown_maps_to_markdown(self):
        assert OutputFormat.MARKDOWN.to_example_format() == ExampleFormat.MARKDOWN

    def test_legacy_json_maps_to_json(self):
        assert OutputFormat.JSON.to_example_format() == ExampleFormat.JSON

    def test_all_values_have_a_mapping(self):
        """Every OutputFormat member must resolve to a valid ExampleFormat without raising."""
        for member in OutputFormat:
            result = member.to_example_format()
            assert isinstance(result, ExampleFormat)
