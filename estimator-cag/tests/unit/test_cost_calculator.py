import pytest
from app.services.helpers.cost_calculator import CostCalculator


@pytest.fixture
def calc() -> CostCalculator:
    return CostCalculator()


# ---------------------------------------------------------------------------
# compute_cost — base cases
# ---------------------------------------------------------------------------

def test_compute_cost_basic(calc: CostCalculator):
    # 1000 input @ $3/1M + 500 output @ $15/1M = 0.003 + 0.0075 = 0.0105
    result = calc.compute_cost(1_000, 500, price_in=3.0, price_out=15.0)
    assert pytest.approx(result, rel=1e-6) == 0.0105


def test_compute_cost_zero_tokens_returns_zero(calc: CostCalculator):
    assert calc.compute_cost(0, 0, price_in=3.0, price_out=15.0) == 0.0


def test_compute_cost_only_input_tokens(calc: CostCalculator):
    # 2000 input @ $1/1M, 0 output
    result = calc.compute_cost(2_000, 0, price_in=1.0, price_out=0.0)
    assert pytest.approx(result, rel=1e-6) == 0.002


def test_compute_cost_only_output_tokens(calc: CostCalculator):
    # 0 input, 1000 output @ $5/1M
    result = calc.compute_cost(0, 1_000, price_in=0.0, price_out=5.0)
    assert pytest.approx(result, rel=1e-6) == 0.005


# ---------------------------------------------------------------------------
# compute_cost — cache adjustments
# ---------------------------------------------------------------------------

def test_compute_cost_with_cache_write(calc: CostCalculator):
    # base: 1000 * 3 / 1M = 0.003
    # cache_write: 500 * 3 * 1.25 / 1M = 0.001875
    result = calc.compute_cost(
        1_000, 0, price_in=3.0, price_out=0.0,
        cache_creation_tokens=500, cache_write_multiplier=1.25,
    )
    assert pytest.approx(result, rel=1e-6) == 0.003 + 0.001875


def test_compute_cost_with_cache_read(calc: CostCalculator):
    # base: 1000 * 3 / 1M = 0.003
    # cache_read: 800 * 3 * 0.1 / 1M = 0.00024
    result = calc.compute_cost(
        1_000, 0, price_in=3.0, price_out=0.0,
        cache_read_tokens=800, cache_read_multiplier=0.1,
    )
    assert pytest.approx(result, rel=1e-6) == 0.003 + 0.00024


def test_compute_cost_cache_multiplier_zero_adds_nothing(calc: CostCalculator):
    # Multipliers default to 0.0 → cache tokens have no effect
    without_cache = calc.compute_cost(1_000, 500, price_in=3.0, price_out=15.0)
    with_cache = calc.compute_cost(
        1_000, 500, price_in=3.0, price_out=15.0,
        cache_creation_tokens=1_000, cache_read_tokens=1_000,
    )
    assert pytest.approx(without_cache) == with_cache


def test_compute_cost_full_cache_scenario(calc: CostCalculator):
    # Anthropic-style: write x1.25, read x0.1
    # base: 2000*3 + 1000*15 = 6000+15000 = 21000 / 1M = 0.021
    # write: 500*3*1.25 / 1M = 0.001875
    # read: 300*3*0.1 / 1M = 0.00009
    result = calc.compute_cost(
        2_000, 1_000, price_in=3.0, price_out=15.0,
        cache_creation_tokens=500, cache_read_tokens=300,
        cache_write_multiplier=1.25, cache_read_multiplier=0.1,
    )
    assert pytest.approx(result, rel=1e-6) == 0.021 + 0.001875 + 0.00009


# ---------------------------------------------------------------------------
# estimate_precall_cost
# ---------------------------------------------------------------------------

def test_estimate_precall_cost_basic(calc: CostCalculator):
    # 500 tokens @ $3/1M = 0.0015
    result = calc.estimate_precall_cost(500, price_in=3.0)
    assert pytest.approx(result, rel=1e-6) == 0.0015


def test_estimate_precall_cost_zero_tokens(calc: CostCalculator):
    assert calc.estimate_precall_cost(0, price_in=3.0) == 0.0


def test_estimate_precall_cost_zero_price(calc: CostCalculator):
    assert calc.estimate_precall_cost(1_000, price_in=0.0) == 0.0


def test_estimate_precall_cost_large_tokens(calc: CostCalculator):
    # 1M tokens @ $0.15/1M = $0.15
    result = calc.estimate_precall_cost(1_000_000, price_in=0.15)
    assert pytest.approx(result, rel=1e-6) == 0.15
