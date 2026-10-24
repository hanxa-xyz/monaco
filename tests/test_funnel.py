import pandas as pd
import pytest

from monaco import funnel as fn
from monaco.io import load
from monaco.paths import SQL_DIR


@pytest.fixture(scope='module')
def events(sandbox_db):
    ev = load(db=sandbox_db, sql=SQL_DIR / 'funnel_events.sql')
    assert set(ev.columns) >= {'account_id', 'partner_id', 'event', 'ts'}
    return ev


def test_prepare_derives_first_trade(events):
    ev, stages = fn.prepare(events, fn.DEFAULT_STAGES, 'trade')
    assert stages[-1] == 'first_trade' and 'first_trade' in set(ev.event)


def test_stage_table_is_one_row_per_account(events):
    ev, stages = fn.prepare(events)
    st = fn.stage_table(ev, stages)
    assert st.account_id.is_unique
    assert st['created'].notna().all()
    assert (st['funded'].isna() | (st['funded'] >= st['created'] - pd.Timedelta(days=1))).mean() > 0.99


def test_conversion_is_censored_and_bounded(events):
    ev, stages = fn.prepare(events)
    st = fn.stage_table(ev, stages)
    as_of = ev.ts.max()
    conv, summ, _ = fn.conversion(st, stages, 'partner_id', 30, as_of, min_n=20)
    rate_cols = [c for c in conv.columns if c.startswith('rate_')]
    assert rate_cols and conv[rate_cols].stack().between(0, 1).all()
    assert 'POOLED (account-weighted)' in summ.index
    # censoring: nobody created within the window counts in the denominator
    assert conv.n.sum() <= (st['created'] <= as_of - pd.Timedelta(days=30)).sum()


def test_funnel_rates_are_monotone_down_the_stages(events):
    ev, stages = fn.prepare(events)
    st = fn.stage_table(ev, stages)
    _, summ, _ = fn.conversion(st, stages, 'partner_id', 30, ev.ts.max(), min_n=20)
    pooled = summ.loc['POOLED (account-weighted)']
    rates = [pooled[f'rate_{s}'] for s in stages[1:]]
    assert all(a >= b - 1e-9 for a, b in zip(rates, rates[1:])), rates


def test_retention_triangle_has_nan_for_incomplete_ages(events):
    ev, stages = fn.prepare(events)
    st = fn.stage_table(ev, stages)
    fig, tri, pooled, note = fn.retention(ev, st, ev.ts.max(), anchor='funded', activity_event='trade', max_age=6, min_cohort=20)
    assert fig is not None and tri.shape[0] >= 3
    assert tri.isna().any().any(), 'the newest cohort cannot have every age complete'
    assert pooled.between(0, 1).all()
