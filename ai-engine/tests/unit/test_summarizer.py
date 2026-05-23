"""Unit tests for SummarizerService and anchor generation."""

import pytest

from app.services.summarizer_service import (
    Anchor,
    AnchorType,
    SummarizerService,
)


class TestSummarizerService:
    """Test anchor detection and accumulative summarization."""

    def test_metadata_extraction_project_name(self):
        """Test detection of project name mentions."""
        summarizer = SummarizerService()
        text = "The project is called MyAppName and will handle real-time data processing."

        anchors = summarizer.process_turn(1, text, None)

        assert len(anchors) > 0
        metadata_anchors = [a for a in anchors if a.anchor_type == "metadata_extraction"]
        assert len(metadata_anchors) > 0
        assert any("project_name" in a.key_information for a in metadata_anchors)

    def test_metadata_extraction_team_size(self):
        """Test detection of team size mentions."""
        summarizer = SummarizerService()
        text = "We have a team of 5 developers working on this project."

        anchors = summarizer.process_turn(1, text, None)

        assert len(anchors) > 0
        metadata_anchors = [a for a in anchors if a.anchor_type == "metadata_extraction"]
        assert any("team_size" in a.key_information for a in metadata_anchors)

    def test_technology_mentions(self):
        """Test detection of technology stack mentions."""
        summarizer = SummarizerService()
        text = "We will use React for the frontend and FastAPI for the backend with PostgreSQL."

        anchors = summarizer.process_turn(1, text, None)

        assert len(anchors) > 0
        tech_anchors = [a for a in anchors if a.anchor_type == "technology_mentioned"]
        assert len(tech_anchors) > 0
        assert any(
            tech in tech_anchors[0].key_information
            for tech in ["React", "FastAPI", "PostgreSQL"]
        )

    def test_decision_point_detection(self):
        """Test detection of decision points."""
        summarizer = SummarizerService()
        text = "We have decided to use GraphQL for the API instead of REST endpoints."

        anchors = summarizer.process_turn(1, text, None)

        decision_anchors = [a for a in anchors if a.anchor_type == "decision_point"]
        assert len(decision_anchors) > 0

    def test_risk_identification(self):
        """Test detection of risk mentions."""
        summarizer = SummarizerService()
        text = "There is a risk that the legacy system integration might fail due to outdated APIs."

        anchors = summarizer.process_turn(1, text, None)

        risk_anchors = [a for a in anchors if a.anchor_type == "risk_identified"]
        assert len(risk_anchors) > 0

    def test_scope_change_detection(self):
        """Test detection of scope changes."""
        summarizer = SummarizerService()
        text = "We also need to include mobile app support and real-time notifications."

        anchors = summarizer.process_turn(1, text, None)

        scope_anchors = [a for a in anchors if a.anchor_type == "scope_change"]
        assert len(scope_anchors) > 0

    def test_contradiction_detection(self):
        """Test detection of contradictions."""
        summarizer = SummarizerService()
        text = "First we said it would be 2 weeks, but actually the timeline is much longer."

        anchors = summarizer.process_turn(1, text, None)

        contradiction_anchors = [a for a in anchors if a.anchor_type == "contradiction_flagged"]
        assert len(contradiction_anchors) > 0

    def test_accumulative_summary(self):
        """Test that summary accumulates across turns."""
        summarizer = SummarizerService()

        # Turn 1: Project metadata
        anchors_1 = summarizer.process_turn(
            1,
            "The project name is SuperApp and we have 4 developers.",
            "Got it, SuperApp with 4 devs.",
        )
        assert len(anchors_1) > 0
        summary_1 = summarizer.get_accumulative_summary()
        assert len(summary_1) > 0

        # Turn 2: Technology and decision
        anchors_2 = summarizer.process_turn(
            2,
            "We decided to use React and Docker for deployment.",
            "Excellent choices for modern development.",
        )
        assert len(anchors_2) > 0
        summary_2 = summarizer.get_accumulative_summary()

        # Summary should accumulate
        assert len(summary_2) >= len(summary_1)
        assert "[METADATA]" in summary_2 or "[TECH]" in summary_2 or "[DECISION]" in summary_2

    def test_anchor_count(self):
        """Test anchor counting."""
        summarizer = SummarizerService()

        assert summarizer.anchor_count() == 0

        summarizer.process_turn(1, "Project name is TestApp with 3 devs.", None)
        count_1 = summarizer.anchor_count()
        assert count_1 > 0

        summarizer.process_turn(2, "We use React and risk: tight timeline.", None)
        count_2 = summarizer.anchor_count()
        assert count_2 >= count_1

    def test_summary_char_count(self):
        """Test summary character counting."""
        summarizer = SummarizerService()

        assert summarizer.summary_char_count() == 0

        summarizer.process_turn(1, "Project: TestApp, 5 engineers, using React and risk: timeline.", None)
        char_count = summarizer.summary_char_count()
        assert char_count > 0

    def test_get_anchors_by_type(self):
        """Test filtering anchors by type."""
        summarizer = SummarizerService()
        summarizer.process_turn(
            1,
            "Project: DataHub, 6 engineers, using React and Python. Risk: scaling.",
            None,
        )

        all_anchors = summarizer.get_anchors()
        assert len(all_anchors) > 0

        tech_anchors = summarizer.get_anchors_by_type("technology_mentioned")
        assert len(tech_anchors) > 0
        assert all(a.anchor_type == "technology_mentioned" for a in tech_anchors)

        risk_anchors = summarizer.get_anchors_by_type("risk_identified")
        assert all(a.anchor_type == "risk_identified" for a in risk_anchors)

    def test_anchor_to_dict(self):
        """Test Anchor serialization."""
        anchor = Anchor(
            turn_number=1,
            anchor_type="metadata_extraction",
            key_information="project_name: TestProject",
            summary="Project name detected",
            message_indices=[0, 1],
        )

        anchor_dict = anchor.to_dict()
        assert anchor_dict["turn_number"] == 1
        assert anchor_dict["anchor_type"] == "metadata_extraction"
        assert anchor_dict["key_information"] == "project_name: TestProject"
        assert anchor_dict["message_indices"] == [0, 1]

    def test_multi_turn_conversation(self):
        """Test a realistic multi-turn conversation with anchor generation."""
        summarizer = SummarizerService()

        # Turn 1: Initial scope
        anchors_1 = summarizer.process_turn(
            1,
            "We want to build an e-commerce platform called ShopHub for 5 team members.",
            "Understood. ShopHub with 5 members.",
        )
        assert any(a.anchor_type == "metadata_extraction" for a in anchors_1)

        # Turn 2: Technology stack
        anchors_2 = summarizer.process_turn(
            2,
            "We will use Next.js, Python FastAPI, and PostgreSQL.",
            "Good stack for modern e-commerce.",
        )
        assert any(a.anchor_type == "technology_mentioned" for a in anchors_2)

        # Turn 3: Risk and decision
        anchors_3 = summarizer.process_turn(
            3,
            "Risk: payment processing complexity. We decided to use Stripe for payments.",
            "Stripe is reliable for this.",
        )
        assert any(a.anchor_type == "risk_identified" for a in anchors_3)
        assert any(a.anchor_type == "decision_point" for a in anchors_3)

        # Turn 4: Scope change
        anchors_4 = summarizer.process_turn(
            4,
            "Actually, we also need mobile app support and real-time inventory updates.",
            "That expands the scope.",
        )
        assert any(a.anchor_type == "scope_change" for a in anchors_4)

        # Verify accumulation
        total_anchors = summarizer.get_anchors()
        assert len(total_anchors) > 0
        summary = summarizer.get_accumulative_summary()
        assert len(summary) > 0

        # Verify turn numbers
        turn_numbers = {a.turn_number for a in total_anchors}
        assert 1 in turn_numbers or 2 in turn_numbers  # At least some turns have anchors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
