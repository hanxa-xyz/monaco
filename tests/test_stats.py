import numpy as np

from monaco.stats import money, pct, wilson


def test_wilson_bounds_and_nan():
    p, lo, hi = wilson([0, 5, 10, 0], [10, 10, 10, 0])
    assert np.allclose(p[:3], [0.0, 0.5, 1.0])
    assert np.isnan(p[3]) and np.isnan(lo[3]) and np.isnan(hi[3])
    assert (lo[:3] <= p[:3] + 1e-12).all() and (p[:3] <= hi[:3] + 1e-12).all()
    assert lo[0] == 0.0 or lo[0] > -1e-12          # never below zero
    assert hi[2] <= 1.0 + 1e-12                      # never above one


def test_wilson_narrows_with_n():
    _, lo1, hi1 = wilson(5, 10)
    _, lo2, hi2 = wilson(500, 1000)
    assert (hi2 - lo2) < (hi1 - lo1)


def test_pct_formatting():
    assert pct(0.1234) == '12%'
    assert pct(0.0123) == '1.2%'
    assert pct(None) == '—' and pct(float('nan')) == '—'


def test_money_formatting():
    assert money(1_234_567) == '$1.2M'
    assert money(12_345) == '$12k'
    assert money(1_234) == '$1,234'
    assert money(-12_345) == '-$12k'
