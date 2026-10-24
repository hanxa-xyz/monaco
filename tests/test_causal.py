import numpy as np
import pandas as pd
import pytest

from monaco import causal as cz


@pytest.fixture(scope='module')
def panel():
    """40 units × 12 periods, unit fixed effects, common seasonality, 10 treated units with a +2.0 effect from period 8."""
    rng = np.random.default_rng(5)
    units = [f'u{i:02d}' for i in range(40)]
    fe = dict(zip(units, rng.normal(10, 2, 40)))
    season = {p: np.sin(p / 2) for p in range(12)}
    rows = []
    for u in units:
        treated = int(u in units[:10])
        for p in range(12):
            y = fe[u] + season[p] + 2.0 * treated * (p >= 8) + rng.normal(0, 0.5)
            rows.append((u, p, y, treated, int(p >= 8)))
    return pd.DataFrame(rows, columns=['unit', 'period', 'y', 'treated', 'post'])


def test_did_recovers_planted_effect(panel):
    res = cz.did(panel, 'unit', 'period', 'y', 'treated', 'post', n_boot=200)
    assert abs(res['att'] - 2.0) < 0.3
    assert res['lo'] < 2.0 < res['hi']
    assert res['n_treated_units'] == 10 and res['n_control_units'] == 30 and res['caveat'] is None
    assert list(res['cells'].index) == ['treated', 'control']


def test_event_study_pre_on_zero_post_on_effect(panel):
    tab, pre = cz.event_study(panel, 'unit', 'period', 'y', 'treated', 8, window=(-5, 3), n_boot=150)
    assert tab.loc[-1, 'coef'] == 0
    assert (tab.loc[[-5, -4, -3, -2], 'coef'].abs() < 0.4).all()
    assert (tab.loc[[0, 1, 2, 3], 'coef'] > 1.4).all()
    assert pre['p'] > 0.01 and pre['df'] == 4


def test_single_treated_unit_sets_caveat(panel):
    one = panel[(panel.treated == 0) | (panel.unit == 'u00')]
    res = cz.did(one, 'unit', 'period', 'y', 'treated', 'post', n_boot=100)
    assert res['caveat'] and 'single unit' in res['caveat']
    assert np.isfinite(res['se'])


def test_cuped_reduces_variance_without_moving_the_point_much():
    rng = np.random.default_rng(7)
    n = 4000
    pre = rng.normal(50, 10, n); arm = rng.choice(['A', 'B'], n)
    y = 0.8 * pre + rng.normal(0, 5, n) + 1.0 * (arm == 'B')
    tab, info = cz.cuped(pd.DataFrame({'y': y, 'pre': pre, 'arm': arm}), 'y', 'pre', 'arm', treatment_label='B')
    assert info['variance_reduction'] > 0.5
    assert tab.loc['cuped', 'se'] < tab.loc['naive', 'se']
    assert abs(tab.loc['cuped', 'diff'] - 1.0) < 0.4


def test_ipw_removes_measured_confounding():
    rng = np.random.default_rng(11)
    n = 6000
    x = rng.normal(0, 1, n)                                    # confounder
    t = (rng.random(n) < 1 / (1 + np.exp(-1.5 * x))).astype(int)
    y = 2.0 * x + 1.0 * t + rng.normal(0, 1, n)                # true effect 1.0
    df = pd.DataFrame({'t': t, 'y': y, 'x': x, 'noise': rng.normal(0, 1, n)})
    res, bal, overlap = cz.ipw(df, 't', 'y', ['x', 'noise'], estimand='ATE', n_boot=100)
    assert abs(res['naive_diff'] - 1.0) > 0.8                  # confounded
    assert abs(res['effect'] - 1.0) < 0.25                     # corrected
    assert bal.loc['x', 'smd_before'] > 0.5 and abs(bal.loc['x', 'smd_after']) < 0.1
    assert 0 < res['ess_treated'] <= res['n_treated']


def test_its_finds_level_change():
    t = np.arange(24); y = 5 + 0.2 * t + 3.0 * (t >= 12)
    tab, info = cz.its(pd.DataFrame({'p': t, 'y': y}), 'p', 'y', 12)
    assert abs(tab.loc['level_change', 'coef'] - 3.0) < 1e-6
    assert abs(tab.loc['slope_change', 'coef']) < 1e-6 and info['n_pre'] == 12


def test_method_ladder_picks_first_yes():
    pick, tab = cz.method_ladder(randomize=False, cutoff=False, panel_pre_post=True, confounders_measured=True)
    assert pick['method'].startswith('Difference-in-differences')
    assert 'parallel trends' in pick['assumption']
    none, _ = cz.method_ladder()
    assert none['method'] is None and len(tab) == 7


def test_plots_run(panel):
    res = cz.did(panel, 'unit', 'period', 'y', 'treated', 'post', n_boot=50)
    tab, pre = cz.event_study(panel, 'unit', 'period', 'y', 'treated', 8, window=(-4, 3), n_boot=50)
    f1, _ = cz.plot_did(panel, 'period', 'y', 'treated', 8, res)
    f2, _ = cz.plot_event_study(tab, pre)
    assert f1 is not None and f2 is not None
    import matplotlib.pyplot as plt
    plt.close('all')
