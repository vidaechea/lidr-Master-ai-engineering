"""Unit tests for app.services.evaluation — pure regex/parsing, no I/O."""
import pytest

from app.services.evaluation import evaluate_estimation_structure

# --------------------------------------------------------------------------- #
# Fixtures: estimation texts
# --------------------------------------------------------------------------- #

WELL_FORMED = """\
## E-commerce Platform Estimation

### Breakdown

| Task | Hours | Cost |
|------|-------|------|
| Frontend development | 40 | 4,000 EUR |
| Backend API | 60 | 6,000 EUR |

Total hours: 100
Total cost: 10,000 EUR

### Recommended Team
- 2 Senior Developers
- 1 Designer

Estimated Duration: 6 weeks
"""

MISSING_TITLE = """\
### Breakdown

| Task | Hours | Cost |
|------|-------|------|
| Backend API | 100 | 10,000 EUR |

Total hours: 100
Total cost: 10,000 EUR

### Recommended Team
- 1 Developer

Estimated Duration: 4 weeks
"""

MISSING_TABLE = """\
## Platform Estimation

Backend: 100 hours

Total hours: 100
Total cost: 10,000 EUR

### Recommended Team
- 1 Developer

Estimated Duration: 4 weeks
"""

MISSING_TOTALS = """\
## Platform Estimation

| Task | Hours | Cost |
|------|-------|------|
| Backend | 100 | 10,000 EUR |

### Recommended Team
- 1 Developer

Estimated Duration: 4 weeks
"""

MISSING_TEAM = """\
## Platform Estimation

| Task | Hours | Cost |
|------|-------|------|
| Backend | 100 | 10,000 EUR |

Total hours: 100
Total cost: 10,000 EUR

Estimated Duration: 4 weeks
"""

MISSING_DURATION = """\
## Platform Estimation

| Task | Hours | Cost |
|------|-------|------|
| Backend | 100 | 10,000 EUR |

Total hours: 100
Total cost: 10,000 EUR

### Recommended Team
- 1 Developer
"""

HOURS_MISMATCH = """\
## Platform Estimation

| Task | Hours | Cost |
|------|-------|------|
| Backend | 50 | 5,000 EUR |
| Frontend | 50 | 5,000 EUR |

Total hours: 999
Total cost: 10,000 EUR

### Recommended Team
- 1 Developer

Estimated Duration: 4 weeks
"""

COST_MISMATCH = """\
## Platform Estimation

| Task | Hours | Cost |
|------|-------|------|
| Backend | 50 | 5,000 EUR |
| Frontend | 50 | 5,000 EUR |

Total hours: 100
Total cost: 99,999 EUR

### Recommended Team
- 1 Developer

Estimated Duration: 4 weeks
"""

EMPTY_TEXT = ""


# --------------------------------------------------------------------------- #
# StructureCheck fields: individual section detection
# --------------------------------------------------------------------------- #

class TestHasTitle:
    def test_detected_when_h2_present(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.has_title is True

    def test_not_detected_when_h2_absent(self):
        result = evaluate_estimation_structure(MISSING_TITLE, "stop")
        assert result.has_title is False

    def test_not_detected_on_empty_text(self):
        result = evaluate_estimation_structure(EMPTY_TEXT, "stop")
        assert result.has_title is False

    def test_h1_does_not_count_as_title(self):
        text = "# Top-level heading\nNo H2 here."
        result = evaluate_estimation_structure(text, "stop")
        assert result.has_title is False


class TestHasBreakdownTable:
    def test_detected_when_table_present(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.has_breakdown_table is True

    def test_not_detected_when_table_absent(self):
        result = evaluate_estimation_structure(MISSING_TABLE, "stop")
        assert result.has_breakdown_table is False

    def test_case_insensitive_header(self):
        text = "## Title\n\n| task | hours | cost |\n|---|---|---|\n| Work | 10 | 100 EUR |\n\nTotal hours: 10\nTotal cost: 100\n\nRecommended Team\n- 1 Dev\n\nDuration: 2 weeks\n"
        result = evaluate_estimation_structure(text, "stop")
        assert result.has_breakdown_table is True


class TestHasTotalsSection:
    def test_detected_when_both_totals_present(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.has_totals_section is True

    def test_not_detected_when_totals_absent(self):
        result = evaluate_estimation_structure(MISSING_TOTALS, "stop")
        assert result.has_totals_section is False

    def test_not_detected_when_only_hours_total_present(self):
        text = "## T\n\n| Task | Hours | Cost |\n|---|---|---|\n| A | 10 | 100 EUR |\n\nTotal hours: 10\n\nRecommended Team\n- 1 Dev\n\nDuration: 2 weeks\n"
        result = evaluate_estimation_structure(text, "stop")
        assert result.has_totals_section is False

    def test_not_detected_when_only_cost_total_present(self):
        text = "## T\n\n| Task | Hours | Cost |\n|---|---|---|\n| A | 10 | 100 EUR |\n\nTotal cost: 100\n\nRecommended Team\n- 1 Dev\n\nDuration: 2 weeks\n"
        result = evaluate_estimation_structure(text, "stop")
        assert result.has_totals_section is False


class TestHasTeamSection:
    def test_detected_when_recommended_team_present(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.has_team_section is True

    def test_not_detected_when_team_absent(self):
        result = evaluate_estimation_structure(MISSING_TEAM, "stop")
        assert result.has_team_section is False

    def test_detected_with_team_composition_phrase(self):
        text = "## T\n\n| Task | Hours | Cost |\n|---|---|---|\n| A | 10 | 100 EUR |\n\nTotal hours: 10\nTotal cost: 100\n\nTeam composition:\n- 1 Dev\n\nDuration: 2 weeks\n"
        result = evaluate_estimation_structure(text, "stop")
        assert result.has_team_section is True


class TestHasDurationSection:
    def test_detected_when_weeks_present(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.has_duration_section is True

    def test_not_detected_when_duration_absent(self):
        result = evaluate_estimation_structure(MISSING_DURATION, "stop")
        assert result.has_duration_section is False

    def test_detected_with_duration_colon_pattern(self):
        text = "## T\n\n| Task | Hours | Cost |\n|---|---|---|\n| A | 10 | 100 EUR |\n\nTotal hours: 10\nTotal cost: 100\n\nRecommended Team\n- 1 Dev\n\nDuration: 3 months\n"
        result = evaluate_estimation_structure(text, "stop")
        assert result.has_duration_section is True


# --------------------------------------------------------------------------- #
# finish_reason validation
# --------------------------------------------------------------------------- #

class TestFinishReasonOk:
    @pytest.mark.parametrize("reason", ["stop", "end_turn"])
    def test_ok_for_valid_finish_reasons(self, reason: str):
        result = evaluate_estimation_structure(WELL_FORMED, reason)
        assert result.finish_reason_ok is True

    @pytest.mark.parametrize("reason", ["max_tokens", "length", "unknown", ""])
    def test_not_ok_for_invalid_finish_reasons(self, reason: str):
        result = evaluate_estimation_structure(WELL_FORMED, reason)
        assert result.finish_reason_ok is False

    def test_bad_finish_reason_appears_in_issues(self):
        result = evaluate_estimation_structure(WELL_FORMED, "max_tokens")
        assert any("finish_reason" in issue for issue in result.issues)


# --------------------------------------------------------------------------- #
# Hours and cost arithmetic checks
# --------------------------------------------------------------------------- #

class TestHoursMatch:
    def test_match_when_sum_equals_declared(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.hours_match is True

    def test_mismatch_when_declared_differs(self):
        result = evaluate_estimation_structure(HOURS_MISMATCH, "stop")
        assert result.hours_match is False

    def test_mismatch_appears_in_issues(self):
        result = evaluate_estimation_structure(HOURS_MISMATCH, "stop")
        assert any("hours mismatch" in issue.lower() for issue in result.issues)

    def test_none_when_no_table_rows(self):
        result = evaluate_estimation_structure(MISSING_TABLE, "stop")
        assert result.hours_match is None

    def test_declared_total_hours_parsed(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.declared_total_hours == 100

    def test_sum_row_hours_computed(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.sum_row_hours == 100


class TestCostMatch:
    def test_match_when_sum_equals_declared(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.cost_match is True

    def test_mismatch_when_declared_differs_beyond_tolerance(self):
        result = evaluate_estimation_structure(COST_MISMATCH, "stop")
        assert result.cost_match is False

    def test_mismatch_appears_in_issues(self):
        result = evaluate_estimation_structure(COST_MISMATCH, "stop")
        assert any("cost mismatch" in issue.lower() for issue in result.issues)

    def test_none_when_no_table_rows(self):
        result = evaluate_estimation_structure(MISSING_TABLE, "stop")
        assert result.cost_match is None

    def test_declared_total_cost_parsed(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.declared_total_cost == 10_000.0

    def test_sum_row_cost_computed(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.sum_row_cost == 10_000.0


# --------------------------------------------------------------------------- #
# Score calculation
# --------------------------------------------------------------------------- #

class TestScore:
    def test_perfect_score_on_well_formed_estimation(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.score == 1.0

    def test_score_is_between_zero_and_one(self):
        for text in [WELL_FORMED, MISSING_TITLE, EMPTY_TEXT]:
            result = evaluate_estimation_structure(text, "stop")
            assert 0.0 <= result.score <= 1.0

    def test_score_decreases_when_sections_missing(self):
        perfect = evaluate_estimation_structure(WELL_FORMED, "stop")
        partial = evaluate_estimation_structure(MISSING_TITLE, "stop")
        assert partial.score < perfect.score

    def test_score_zero_on_empty_text_with_bad_finish_reason(self):
        result = evaluate_estimation_structure(EMPTY_TEXT, "length")
        assert result.score == 0.0


# --------------------------------------------------------------------------- #
# Issues list
# --------------------------------------------------------------------------- #

class TestIssues:
    def test_no_issues_on_well_formed_estimation(self):
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert result.issues == []

    def test_missing_title_generates_issue(self):
        result = evaluate_estimation_structure(MISSING_TITLE, "stop")
        assert any("title" in issue.lower() for issue in result.issues)

    def test_missing_table_generates_issue(self):
        result = evaluate_estimation_structure(MISSING_TABLE, "stop")
        assert any("breakdown table" in issue.lower() for issue in result.issues)

    def test_missing_totals_generates_issue(self):
        result = evaluate_estimation_structure(MISSING_TOTALS, "stop")
        assert any("totals" in issue.lower() for issue in result.issues)

    def test_missing_team_generates_issue(self):
        result = evaluate_estimation_structure(MISSING_TEAM, "stop")
        assert any("team" in issue.lower() for issue in result.issues)

    def test_missing_duration_generates_issue(self):
        result = evaluate_estimation_structure(MISSING_DURATION, "stop")
        assert any("duration" in issue.lower() for issue in result.issues)

    def test_all_issues_present_on_empty_text(self):
        result = evaluate_estimation_structure(EMPTY_TEXT, "length")
        issue_text = " ".join(result.issues).lower()
        assert "title" in issue_text
        assert "breakdown table" in issue_text
        assert "totals" in issue_text
        assert "team" in issue_text
        assert "duration" in issue_text
        assert "finish_reason" in issue_text


# --------------------------------------------------------------------------- #
# Return type
# --------------------------------------------------------------------------- #

class TestReturnType:
    def test_returns_structure_check_instance(self):
        from app.schemas.estimation import StructureCheck
        result = evaluate_estimation_structure(WELL_FORMED, "stop")
        assert isinstance(result, StructureCheck)

    def test_score_is_rounded_to_three_decimals(self):
        result = evaluate_estimation_structure(MISSING_TITLE, "stop")
        # score should not have more than 3 decimal places
        assert result.score == round(result.score, 3)
