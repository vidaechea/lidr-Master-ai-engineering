import pytest

from app.domain.schemas.estimation import ExampleFormat
from app.domain.schemas.estimation import OutputFormat


class TestOutputFormatEnum:
    """Test OutputFormat enum values and structure."""

    def test_output_format_has_three_values(self):
        """OutputFormat should have exactly three values."""
        values = list(OutputFormat)
        assert len(values) == 3
        assert OutputFormat.PHASES_TABLE in values
        assert OutputFormat.LINE_ITEMS in values
        assert OutputFormat.NARRATIVE in values

    def test_phases_table_value(self):
        assert OutputFormat.PHASES_TABLE.value == "phases_table"

    def test_line_items_value(self):
        assert OutputFormat.LINE_ITEMS.value == "line_items"

    def test_narrative_value(self):
        assert OutputFormat.NARRATIVE.value == "narrative"


class TestExampleFormatEnum:
    """Test ExampleFormat enum values and structure."""

    def test_example_format_has_three_values(self):
        """ExampleFormat should have exactly three values."""
        values = list(ExampleFormat)
        assert len(values) == 3
        assert ExampleFormat.MARKDOWN in values
        assert ExampleFormat.JSON in values
        assert ExampleFormat.NARRATIVE in values

    def test_markdown_value(self):
        assert ExampleFormat.MARKDOWN.value == "markdown"

    def test_json_value(self):
        assert ExampleFormat.JSON.value == "json"

    def test_narrative_value(self):
        assert ExampleFormat.NARRATIVE.value == "narrative"

