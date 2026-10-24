import numpy as np
import pandas as pd
import pytest

from monaco import survival as sv


@pytest.fixture(scope='module')
def exp_data():
    """Exponential lifetimes with rate 1/10 (true median 6.93) and independent censoring; 2 groups with different rates."""
    rng = np.random.default_rng(1)
    n = 2000
    g = rng.choice(['fast', 'slow'], n)
    rate = np.where(g == 'fast', 1 / 5, 1 / 15)
    t = rng.exponential(1 / rate)
    c = rng.exponential(20, n)
    return pd.DataFrame({'duration': np.minimum(t, c), 'event': (t <= c).astype(int), 'group': g, 'true_t': t})


def test_km_matches_textbook_small_example():
    # classic: times 1,2,3+,4,5+ (+ = censored): S = 1 -> .8 -> .6 -> .6 -> .3 -> .3
    tab = sv.km([1, 2, 3, 4, 5], [1, 1, 0, 1, 0])
    assert np.allclose(tab.S.values, [1.0, 0.8, 0.6, 0.3])
    assert list(tab.n_risk) == [5, 5, 4, 2]
    assert (tab.lo <= tab.S + 1e-12).all() and (tab.hi >= tab.S - 1e-12).all()
    assert (tab.lo >= 0).all() and (tab.hi <= 1).all()


def test_km_recovers_exponential_survival(exp_data):
    d = exp_data[exp_data.group == 'slow']
    tab = sv.km(d.duration, d.event)
    s = sv.survival_at(tab, [5, 10, 15])
    truth = np.exp(-np.array([5, 10, 15]) / 15)
    assert np.allclose(s.S.values, truth, atol=0.04)
    assert abs(sv.median_survival(tab) - 15 * np.log(2)) < 1.5


def test_naive_reads_bracket_km(exp_data):
    cmp = sv.naive_vs_km(exp_data, [5, 10, 20])
    # dropping censored biases survival down; counting censored as survivors biases it up
    assert (cmp.naive_known_status_only <= cmp.km_S + 1e-9).all()
    assert (cmp.naive_censored_as_survivors >= cmp.km_S - 1e-9).all()


def test_logrank_separates_groups_and_not_noise(exp_data):
    chi2, dof, p, tab = sv.logrank(exp_data)
    assert dof == 1 and p < 1e-6 and chi2 > 30
    noise = exp_data.assign(group=np.random.default_rng(2).choice(['a', 'b'], len(exp_data)))
    _, _, p2, _ = sv.logrank(noise)
    assert p2 > 0.01


def test_rmst_and_hazard_window(exp_data):
    tab = sv.km(exp_data.duration, exp_data.event)
    r = sv.rmst(tab, 10)
    assert 0 < r < 10
    t0, t1, drop = sv.hazard_window(tab, 2)
    assert t0 == 0.0 and drop > 0          # exponential: hazard constant, so the biggest drop in S is the first bin


def test_from_timestamps_censors_at_as_of():
    df = pd.DataFrame({'start': pd.to_datetime(['2026-01-01', '2026-01-10', '2026-02-01', '2026-03-05']),
                       'end': pd.to_datetime(['2026-01-15', None, '2026-03-01', None]), 'g': list('aabb')})
    d = sv.from_timestamps(df, 'start', 'end', as_of='2026-02-15', group='g')
    assert len(d) == 3                                   # the March start is after as_of
    assert list(d.event) == [1, 0, 0]                    # Feb 1 -> Mar 1 is after as_of, so censored at as_of
    assert d.duration.iloc[1] == pytest.approx(36)


def test_plot_km_runs(exp_data):
    curves = {'all': sv.km(exp_data.duration, exp_data.event)}
    for g, d in exp_data.groupby('group'):
        curves[g] = sv.km(d.duration, d.event)
    fig, note = sv.plot_km(curves, [5, 10, 20], 'days')
    assert fig is not None and 'censored' in note
    import matplotlib.pyplot as plt
    plt.close('all')
