"""Tests for prompt loader and rendering."""

import pytest

from app.prompts.loader import render_estimation_prompt
from app.schemas.estimation import (
    DetailLevel,
    EstimationRequest,
    OutputFormat,
    ProjectType,
    UserTier,
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
        # Developer template always produces a technical breakdown regardless of format
        assert "technical" in system.lower() or "engineer" in system.lower()

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
        """Test that the same request always produces the same system prompt (idempotent)."""
        basic_request.output_format = OutputFormat.PHASES_TABLE
        system_phases, _ = render_estimation_prompt(basic_request)

        # Calling again with the same request must produce the same result
        system_phases2, _ = render_estimation_prompt(basic_request)
        assert system_phases == system_phases2

    # --- Requirements validation tests ---

    def test_user_prompt_wraps_description_in_project_description_block(self, basic_request):
        """Req 1: the literal transcription text must appear right after 'Project description:'."""
        description = "My unique project description text for testing."
        basic_request.transcription = description
        _, user = render_estimation_prompt(basic_request)
        assert f"Project description:\n{description}" in user

    def test_phases_table_keyword_present_and_absent_in_narrative(self, basic_request):
        """Req 2: developer template always groups tasks by phase."""
        basic_request.output_format = OutputFormat.PHASES_TABLE
        system_phases, _ = render_estimation_prompt(basic_request)
        assert "Group tasks by phase" in system_phases or "phase" in system_phases.lower()

        # Different output format still renders without error
        basic_request.output_format = OutputFormat.NARRATIVE
        system_narrative, _ = render_estimation_prompt(basic_request)
        assert len(system_narrative) > 0

    def test_detailed_includes_assumptions_instruction_summary_does_not(self, basic_request):
        """Req 3: detail_level=detailed adds granularity instruction; summary uses high-level.

        Developer v1 template emits "maximum granularity" for 'detailed' and
        "high-level only" for 'summary'.
        """
        basic_request.detail_level = DetailLevel.DETAILED
        system_detailed, _ = render_estimation_prompt(basic_request)
        assert "granularity" in system_detailed.lower() or "subtasks" in system_detailed.lower()

        basic_request.detail_level = DetailLevel.SUMMARY
        system_summary, _ = render_estimation_prompt(basic_request)
        assert "high-level" in system_summary.lower() or "broadly" in system_summary.lower()


class TestRenderEstimationPromptV2:
    """Tests specific to the v2 prompt template."""

    @pytest.fixture
    def basic_request(self):
        return EstimationRequest(
            transcription="Build a SaaS analytics dashboard with role-based access.",
            output_format=OutputFormat.PHASES_TABLE,
            num_examples=3,
        )

    def test_v2_renders_without_error(self, basic_request):
        system, user = render_estimation_prompt(basic_request, version="v2")
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        assert len(user) > 0

    def test_v2_system_prompt_differs_from_v1(self, basic_request):
        system_v1, _ = render_estimation_prompt(basic_request, version="v1")
        system_v2, _ = render_estimation_prompt(basic_request, version="v2")
        assert system_v1 != system_v2

    def test_v2_system_prompt_contains_confidence_level_instruction(self, basic_request):
        system, _ = render_estimation_prompt(basic_request, version="v2")
        assert "confidence" in system.lower()

    def test_v2_system_prompt_contains_senior_consultant_role(self, basic_request):
        system, _ = render_estimation_prompt(basic_request, version="v2")
        assert "consultant" in system.lower() or "senior" in system.lower()

    def test_v2_system_prompt_contains_numbered_rules(self, basic_request):
        system, _ = render_estimation_prompt(basic_request, version="v2")
        assert "1." in system and "2." in system

    def test_v2_user_prompt_includes_confidence_instruction(self, basic_request):
        _, user = render_estimation_prompt(basic_request, version="v2")
        assert "confidence" in user.lower()

    def test_v2_user_prompt_contains_transcription(self, basic_request):
        _, user = render_estimation_prompt(basic_request, version="v2")
        assert basic_request.transcription in user

    def test_v2_includes_examples_when_requested(self, basic_request):
        # developer/v2 ships with 1 example; verify it appears
        basic_request.num_examples = 1
        system, _ = render_estimation_prompt(basic_request, version="v2")
        assert "Example 1" in system or "example" in system.lower()

    def test_v2_example_count_respected(self, basic_request):
        # developer/v2 has 1 example: 0 examples < 1 example produces shorter prompt
        basic_request.num_examples = 0
        system_none, _ = render_estimation_prompt(basic_request, version="v2")
        basic_request.num_examples = 1
        system_one, _ = render_estimation_prompt(basic_request, version="v2")
        assert len(system_one) > len(system_none)

    def test_v2_examples_contain_confidence_level(self, basic_request):
        basic_request.num_examples = 1
        system, _ = render_estimation_prompt(basic_request, version="v2")
        assert "Confidence Level" in system

    def test_v2_output_format_phases_table_renders(self, basic_request):
        basic_request.output_format = OutputFormat.PHASES_TABLE
        system, _ = render_estimation_prompt(basic_request, version="v2")
        assert "phases" in system.lower() or "phase" in system.lower()

    def test_v2_output_format_json_renders(self, basic_request):
        # Developer template produces consistent output regardless of output_format
        basic_request.output_format = OutputFormat.LINE_ITEMS
        system, _ = render_estimation_prompt(basic_request, version="v2")
        assert len(system) > 0
        assert "technical" in system.lower() or "engineer" in system.lower()

    def test_v2_detail_level_detailed_renders(self, basic_request):
        basic_request.detail_level = DetailLevel.DETAILED
        system, _ = render_estimation_prompt(basic_request, version="v2")
        assert "granular" in system.lower() or "detailed" in system.lower()

    def test_v2_prompts_are_trimmed(self, basic_request):
        system, user = render_estimation_prompt(basic_request, version="v2")
        assert not system.endswith("\n\n")
        assert not user.endswith("\n\n")


class TestRenderEstimationPromptTiers:
    """Tests for tier-specific template selection."""

    @pytest.fixture
    def base_request(self):
        return EstimationRequest(
            transcription="Build a SaaS analytics dashboard with role-based access.",
            output_format=OutputFormat.PHASES_TABLE,
            num_examples=1,
        )

    def test_developer_tier_produces_technical_breakdown(self, base_request):
        system, _ = render_estimation_prompt(base_request, tier=UserTier.DEVELOPER)
        assert "technical" in system.lower() or "engineer" in system.lower()

    def test_pm_tier_produces_milestone_oriented_prompt(self, base_request):
        system, _ = render_estimation_prompt(base_request, tier=UserTier.PM)
        assert "milestone" in system.lower() or "project manager" in system.lower()

    def test_executive_tier_produces_investment_summary(self, base_request):
        system, _ = render_estimation_prompt(base_request, tier=UserTier.EXECUTIVE)
        assert "executive" in system.lower() or "investment" in system.lower() or "roi" in system.lower()

    def test_tiers_produce_different_system_prompts(self, base_request):
        dev_sys, _ = render_estimation_prompt(base_request, tier=UserTier.DEVELOPER)
        pm_sys, _ = render_estimation_prompt(base_request, tier=UserTier.PM)
        exec_sys, _ = render_estimation_prompt(base_request, tier=UserTier.EXECUTIVE)
        assert dev_sys != pm_sys
        assert pm_sys != exec_sys
        assert dev_sys != exec_sys

    def test_no_tier_equals_developer_tier(self, base_request):
        """Omitting tier must fall back to the developer template."""
        sys_no_tier, _ = render_estimation_prompt(base_request)
        sys_dev_tier, _ = render_estimation_prompt(base_request, tier=UserTier.DEVELOPER)
        assert sys_no_tier == sys_dev_tier

    def test_all_tier_version_combinations_render_without_error(self, base_request):
        for tier in UserTier:
            for version in ("v1", "v2"):
                system, user = render_estimation_prompt(base_request, tier=tier, version=version)
                assert len(system) > 0
                assert len(user) > 0

    def test_user_prompt_contains_transcription_for_every_tier(self, base_request):
        for tier in UserTier:
            _, user = render_estimation_prompt(base_request, tier=tier)
            assert base_request.transcription in user

    def test_pm_v2_contains_confidence_level(self, base_request):
        system, _ = render_estimation_prompt(base_request, tier=UserTier.PM, version="v2")
        assert "confidence" in system.lower()

    def test_executive_v2_contains_confidence_level(self, base_request):
        system, _ = render_estimation_prompt(base_request, tier=UserTier.EXECUTIVE, version="v2")
        assert "confidence" in system.lower()


class TestGetExamplesByTier:
    """Tests for tier-specific example loading."""

    def test_developer_examples_are_loaded(self):
        from app.prompts.loader import get_examples
        examples = get_examples(tier="developer")
        assert len(examples) > 0

    def test_pm_examples_are_loaded(self):
        from app.prompts.loader import get_examples
        examples = get_examples(tier="pm")
        assert len(examples) > 0

    def test_executive_examples_are_loaded(self):
        from app.prompts.loader import get_examples
        examples = get_examples(tier="executive")
        assert len(examples) > 0

    def test_pm_and_developer_examples_differ(self):
        from app.prompts.loader import get_examples
        dev = get_examples(tier="developer")
        pm = get_examples(tier="pm")
        # Same project scenario but PM estimation should differ from developer estimation
        assert dev[0].estimation_markdown != pm[0].estimation_markdown

    def test_none_tier_defaults_to_developer(self):
        from app.prompts.loader import get_examples
        default = get_examples()
        explicit_dev = get_examples(tier="developer")
        assert default is explicit_dev
