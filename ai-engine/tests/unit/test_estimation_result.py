import pytest
from app.domain.schemas.estimation import EstimationResult, Phase


def test_estimation_result_total_cost_must_match_phases():
    # 4000 + 8000 = 12000, pero total_cost_eur dice 10000 -> debe fallar
    with pytest.raises(ValueError):
        EstimationResult(
            summary="Test",
            total_duration_weeks=10,
            total_cost_eur=10000,
            confidence_pct=80,
            phases=[
                Phase(name="Design", duration_weeks=4, cost_eur=4000, confidence_pct=90, assumptions=[]),
                Phase(name="Build", duration_weeks=6, cost_eur=8000, confidence_pct=70, assumptions=[]),
            ],
        )


def test_estimation_result_total_cost_matches_phases():
    # 4000 + 6000 = 10000, total_cost_eur = 10000 -> debe pasar
    result = EstimationResult(
        summary="Test",
        total_duration_weeks=10,
        total_cost_eur=10000,
        confidence_pct=80,
        phases=[
            Phase(name="Design", duration_weeks=4, cost_eur=4000, confidence_pct=90, assumptions=[]),
            Phase(name="Build", duration_weeks=6, cost_eur=6000, confidence_pct=70, assumptions=[]),
        ],
    )
    assert result.total_cost_eur == 10000
    assert sum(phase.cost_eur for phase in result.phases) == 10000

