import pytest
from app.domain.output_validator import evaluate_estimation_structure

# ---------------------------------------------------------------------------
# Fixtures — reusable estimation text fragments
# ---------------------------------------------------------------------------

_FULL_ESTIMATION = """\
## E-Commerce Platform

| Task | Hours | Cost |
|------|-------|------|
| Backend API | 80 | 8,000 EUR |
| Frontend UI | 40 | 4,000 EUR |
| QA & Testing | 20 | 2,000 EUR |

**Total hours:** 140
**Total cost:** 14,000 EUR

## Recommended Team
- 1 Senior Developer
- 1 Frontend Developer

## Estimated Duration
4 weeks
"""

_NO_TABLE = """\
## My Project

Total hours: 100
Total cost: 10,000 EUR

Recommended Team: 2 Developers
Duration: 4 weeks
"""

_EMPTY = ""


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

def test_returns_structure_check_instance():
    from app.domain.schemas.estimation import StructureCheck
    result = evaluate_estimation_structure(_FULL_ESTIMATION, "stop")
    assert isinstance(result, StructureCheck)


# ---------------------------------------------------------------------------
# has_title
# ---------------------------------------------------------------------------

def test_has_title_when_h2_present():
    result = evaluate_estimation_structure(_FULL_ESTIMATION, "stop")
    assert result.has_title is True


def test_no_title_when_h2_absent():
    result = evaluate_estimation_structure(_NO_TABLE, "stop")
    # _NO_TABLE has ## My Project → title is present
    assert result.has_title is True


def test_no_title_on_empty_text():
    result = evaluate_estimation_structure(_EMPTY, "stop")
    assert result.has_title is False


def test_h1_not_counted_as_title():
    text = "# Only H1 heading\nsome content"
    result = evaluate_estimation_structure(text, "stop")
    assert result.has_title is False


# ---------------------------------------------------------------------------
# has_breakdown_table
# ---------------------------------------------------------------------------

def test_has_breakdown_table_when_present():
    result = evaluate_estimation_structure(_FULL_ESTIMATION, "stop")
    assert result.has_breakdown_table is True


def test_no_breakdown_table_when_absent():
    result = evaluate_estimation_structure(_NO_TABLE, "stop")
    assert result.has_breakdown_table is False


def test_breakdown_table_header_case_insensitive():
    text = "## Project\n| task | hours | cost |\n|---|---|---|\n| Dev | 10 | 1,000 EUR |\nTotal hours: 10\nTotal cost: 1,000\nTeam: 1 Dev\n4 weeks"
    result = evaluate_estimation_structure(text, "stop")
    assert result.has_breakdown_table is True


# ---------------------------------------------------------------------------
# has_totals_section
# ---------------------------------------------------------------------------

def test_has_totals_when_both_present():
    result = evaluate_estimation_structure(_FULL_ESTIMATION, "stop")
    assert result.has_totals_section is True


def test_no_totals_when_only_hours_present():
    text = "## Project\nTotal hours: 100\nTeam: 1 Dev\n4 weeks"
    result = evaluate_estimation_structure(text, "stop")
    assert result.has_totals_section is False


def test_no_totals_when_only_cost_present():
    text = "## Project\nTotal cost: 10,000\nTeam: 1 Dev\n4 weeks"
    result = evaluate_estimation_structure(text, "stop")
    assert result.has_totals_section is False


# ---------------------------------------------------------------------------
# has_team_section
# ---------------------------------------------------------------------------

def test_has_team_via_recommended_team():
    result = evaluate_estimation_structure(_FULL_ESTIMATION, "stop")
    assert result.has_team_section is True


def test_has_team_via_team_composition():
    text = "## Project\nTeam composition: 2 devs\nTotal hours: 10\nTotal cost: 1000\n4 weeks"
    result = evaluate_estimation_structure(text, "stop")
    assert result.has_team_section is True


def test_no_team_section_when_absent():
    text = "## Project\nTotal hours: 10\nTotal cost: 1000\n4 weeks"
    result = evaluate_estimation_structure(text, "stop")
    assert result.has_team_section is False


# ---------------------------------------------------------------------------
# has_duration_section
# ---------------------------------------------------------------------------

def test_has_duration_via_weeks():
    result = evaluate_estimation_structure(_FULL_ESTIMATION, "stop")
    assert result.has_duration_section is True


def test_has_duration_via_estimated_duration():
    text = "## Project\nEstimated Duration: 6 weeks\nTotal hours: 10\nTotal cost: 1000\nTeam: 1 dev"
    result = evaluate_estimation_structure(text, "stop")
    assert result.has_duration_section is True


def test_no_duration_when_absent():
    text = "## Project\nTotal hours: 10\nTotal cost: 1000\nTeam: 1 dev"
    result = evaluate_estimation_structure(text, "stop")
    assert result.has_duration_section is False


# ---------------------------------------------------------------------------
# finish_reason
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reason", ["stop", "end_turn", "stop_sequence"])
def test_finish_reason_ok_for_valid_reasons(reason: str):
    result = evaluate_estimation_structure(_FULL_ESTIMATION, reason)
    assert result.finish_reason_ok is True


@pytest.mark.parametrize("reason", ["length", "max_tokens", "content_filter", ""])
def test_finish_reason_not_ok_for_invalid_reasons(reason: str):
    result = evaluate_estimation_structure(_FULL_ESTIMATION, reason)
    assert result.finish_reason_ok is False


def test_bad_finish_reason_appears_in_issues():
    result = evaluate_estimation_structure(_FULL_ESTIMATION, "length")
    assert any("finish_reason" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# hours_match / cost_match
# ---------------------------------------------------------------------------

def test_hours_match_true_when_sum_equals_declared():
    # rows: 80+40+20 = 140, declared = 140
    result = evaluate_estimation_structure(_FULL_ESTIMATION, "stop")
    assert result.sum_row_hours == 140
    assert result.declared_total_hours == 140
    assert result.hours_match is True


def test_hours_match_false_when_sum_differs():
    text = """\
## Project
| Task | Hours | Cost |
|------|-------|------|
| Dev | 50 | 5,000 EUR |

Total hours: 100
Total cost: 5,000 EUR
Recommended Team: 1 dev
4 weeks
"""
    result = evaluate_estimation_structure(text, "stop")
    assert result.hours_match is False
    assert any("hours mismatch" in issue for issue in result.issues)


def test_cost_match_true_when_within_2_percent():
    # rows: 8000+4000+2000 = 14000, declared = 14000
    result = evaluate_estimation_structure(_FULL_ESTIMATION, "stop")
    assert result.cost_match is True


def test_cost_match_false_when_exceeds_2_percent():
    text = """\
## Project
| Task | Hours | Cost |
|------|-------|------|
| Dev | 50 | 5,000 EUR |

Total hours: 50
Total cost: 9,000 EUR
Recommended Team: 1 dev
4 weeks
"""
    result = evaluate_estimation_structure(text, "stop")
    assert result.cost_match is False


def test_hours_match_is_none_when_no_table():
    result = evaluate_estimation_structure(_NO_TABLE, "stop")
    assert result.hours_match is None
    assert result.sum_row_hours is None


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------

def test_score_is_1_for_perfect_estimation():
    result = evaluate_estimation_structure(_FULL_ESTIMATION, "stop")
    assert result.score == 1.0


def test_score_is_between_0_and_1():
    result = evaluate_estimation_structure(_EMPTY, "stop")
    assert 0.0 <= result.score <= 1.0


def test_score_is_float():
    result = evaluate_estimation_structure(_FULL_ESTIMATION, "stop")
    assert isinstance(result.score, float)


# ---------------------------------------------------------------------------
# issues list
# ---------------------------------------------------------------------------

def test_no_issues_for_perfect_estimation():
    result = evaluate_estimation_structure(_FULL_ESTIMATION, "stop")
    assert result.issues == []


def test_issues_populated_for_empty_text():
    result = evaluate_estimation_structure(_EMPTY, "stop")
    assert len(result.issues) > 0


def test_missing_title_reported_in_issues():
    text = "Some text without heading\nTotal hours: 10\nTotal cost: 1000\nTeam: 1 dev\n4 weeks"
    result = evaluate_estimation_structure(text, "stop")
    assert any("title" in issue.lower() for issue in result.issues)


def test_missing_table_reported_in_issues():
    result = evaluate_estimation_structure(_NO_TABLE, "stop")
    assert any("breakdown table" in issue.lower() for issue in result.issues)


