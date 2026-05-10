"""Tests for prompt loader and rendering."""

import pytest

from app.prompts.loader import render_estimation_prompt
from app.schemas.estimation import (
    DetailLevel,
    EstimationRequest,
    OutputFormat,
    ProjectType,
)


class TestRenderEstimationPrompt:
    """Test rendering estimation prompts using Jinja2 templates."""

    @pytest.fixture
    def basic_request(self):
        """Provide a basic estimation request for testing."""
        return EstimationRequest(
            transcription="Test project description for estimation.",
            output_format=OutputFormat.PHASES_TABLE,
            num_examples=3,
        )

    def test_render_returns_tuple_of_two_strings(self, basic_request):
        system, user = render_estimation_prompt(basic_request)
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        assert len(user) > 0

    def test_system_prompt_contains_expert_role(self, basic_request):
        system, _ = render_estimation_prompt(basic_request)
        assert "expert" in system.lower() or "estimator" in system.lower()

    def test_user_prompt_contains_project_description(self, basic_request):
        _, user = render_estimation_prompt(basic_request)
        assert "Test project description" in user

    def test_system_prompt_with_phases_table_format(self, basic_request):
        basic_request.output_format = OutputFormat.PHASES_TABLE
        system, _ = render_estimation_prompt(basic_request)
        assert "phases" in system.lower() or "phase" in system.lower()

    def test_system_prompt_with_line_items_format(self, basic_request):
        basic_request.output_format = OutputFormat.LINE_ITEMS
        system, _ = render_estimation_prompt(basic_request)
        assert "line" in system.lower() or "items" in system.lower()

    def test_system_prompt_with_narrative_format(self, basic_request):
        basic_request.output_format = OutputFormat.NARRATIVE
        system, _ = render_estimation_prompt(basic_request)
        assert "narrative" in system.lower() or "prose" in system.lower()

    def test_system_prompt_with_summary_detail_level(self, basic_request):
        basic_request.detail_level = DetailLevel.SUMMARY
        system, _ = render_estimation_prompt(basic_request)
        assert "summary" in system.lower() or "high level" in system.lower()

    def test_system_prompt_with_detailed_detail_level(self, basic_request):
        basic_request.detail_level = DetailLevel.DETAILED
        system, _ = render_estimation_prompt(basic_request)
        assert "detailed" in system.lower() or "granular" in system.lower()

    def test_system_prompt_includes_examples(self, basic_request):
        basic_request.num_examples = 2
        system, _ = render_estimation_prompt(basic_request)
        assert "Example" in system or "example" in system

    def test_examples_count_respected(self, basic_request):
        basic_request.num_examples = 1
        system1, _ = render_estimation_prompt(basic_request)
        basic_request.num_examples = 3
        system3, _ = render_estimation_prompt(basic_request)
        # More examples should make the system prompt longer
        assert len(system3) > len(system1)

    def test_with_project_type_included(self, basic_request):
        basic_request.project_type = ProjectType.WEB_SAAS
        system, _ = render_estimation_prompt(basic_request)
        # The prompt should be well-formed even with project_type
        assert len(system) > 0

    def test_version_defaults_to_v1(self, basic_request):
        system1, user1 = render_estimation_prompt(basic_request, version="v1")
        system2, user2 = render_estimation_prompt(basic_request)
        assert system1 == system2
        assert user1 == user2

    def test_rich_transcription_is_included(self, basic_request):
        rich_text = (
            "Client X needs a platform to manage inventory across multiple warehouses, "
            "with real-time alerts and reporting capabilities."
        )
        basic_request.transcription = rich_text
        _, user = render_estimation_prompt(basic_request)
        assert rich_text in user

    def test_prompts_are_non_empty_after_rendering(self, basic_request):
        system, user = render_estimation_prompt(basic_request)
        assert system.strip()
        assert user.strip()
        assert not system.endswith("\n\n")  # Should be trimmed
        assert not user.endswith("\n\n")  # Should be trimmed

    def test_multiple_calls_with_different_formats(self, basic_request):
        """Test that different formats produce different prompts."""
        basic_request.output_format = OutputFormat.PHASES_TABLE
        system_phases, _ = render_estimation_prompt(basic_request)

        basic_request.output_format = OutputFormat.LINE_ITEMS
        system_items, _ = render_estimation_prompt(basic_request)

        # Prompts should be different for different formats
        assert system_phases != system_items
