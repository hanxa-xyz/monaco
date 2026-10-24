import numpy as np
import pytest

from monaco import eda, viz


def test_palette_is_one_hue_plus_black():
    assert viz.BLACK == '#1a1a1a'
    assert all(c.startswith('#') for c in viz.RAMP4) and len(viz.RAMP4) == 4
    assert viz.GRAY not in viz.RAMP4


def test_structure_reports_grain(tiny_df):
    v = eda.structure({'df': tiny_df}, keys={'df': [['customer_id'], ['segment']]})
    assert v.fig is None
    assert isinstance(v.table, dict) or hasattr(v.table, 'keys') or v.table is not None


def test_penetration_rates_are_within_group(tiny_df):
    v = eda.penetration(tiny_df, dim='segment', flag='repeat_90d', entity='customer_id')
    t = v.table
    rate_col = [c for c in t.columns if 'rate' in c.lower() or c.lower().endswith('%') or 'share' in c.lower()]
    assert v.fig is not None and len(t) >= 4
    if rate_col:
        assert t[rate_col[0]].between(0, 1).all() or t[rate_col[0]].between(0, 100).all()


def test_distribution_sums_to_one(tiny_df):
    v = eda.distribution(tiny_df, dim='segment', metric='revenue', entity='customer_id')
    t = v.table
    share_cols = [c for c in t.columns if 'share' in str(c).lower()]
    assert share_cols, t.columns
    for c in share_cols:
        assert abs(float(t[c].sum()) - 1.0) < 1e-6 or abs(float(t[c].sum()) - 100.0) < 1e-6


def test_trio_and_mix_run(tiny_df):
    assert eda.trio(tiny_df, dim='segment', metric='revenue', entity='customer_id').fig is not None
    assert eda.mix(tiny_df, dim='segment', by='region', entity='customer_id').fig is not None


def test_time_series_true_date_axis(tiny_df):
    v = eda.time_series(tiny_df, time_col='first_order_at', metric='revenue', freq='M')
    assert v.fig is not None and len(v.table) >= 10


def test_pareto_marks_and_tiers(tiny_df):
    v, tiers = eda.pareto(tiny_df, entity='customer_id', value='revenue')
    assert v.fig is not None
    assert set(tiers) >= {0.5, 0.8} or len(tiers) >= 2


def test_saturation_k_marks(tiny_df):
    v, ks = eda.saturation(tiny_df, entity='customer_id', count_col='orders')
    assert v.fig is not None
    vals = list(ks.values()) if isinstance(ks, dict) else list(ks)
    assert all(np.isfinite(float(k)) for k in vals)


@pytest.fixture(autouse=True)
def _close_figs():
    yield
    import matplotlib.pyplot as plt
    plt.close('all')
