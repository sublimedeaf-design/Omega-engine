import math
from omega.market import devig_proportional, evaluate_value


def test_devig_sums_to_one():
    p = devig_proportional([1.80, 3.60, 4.50])
    assert math.isclose(sum(p), 1.0)


def test_value_math():
    d = evaluate_value(0.60, 1.90)
    assert math.isclose(d.fair_odds, 1 / 0.60)
    assert math.isclose(d.break_even_probability, 1 / 1.90)
    assert math.isclose(d.ev, 0.14)
