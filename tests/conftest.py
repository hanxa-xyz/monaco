"""Shared fixtures. Everything is small and in-memory except `sandbox_db`, a tiny synthetic DuckDB built once per session."""
import os

import matplotlib

matplotlib.use('Agg')

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope='session')
def tiny_df():
    rng = np.random.default_rng(0)
    n = 600
    seg = rng.choice(['a', 'b', 'c', 'd'], n, p=[.4, .3, .2, .1])
    df = pd.DataFrame({
        'customer_id': np.arange(n),
        'segment': seg,
        'region': rng.choice(['east', 'west'], n),
        'revenue': rng.gamma(2.0, 50.0, n).round(2),
        'orders': rng.poisson(2.0, n) + 1,
        'repeat_90d': (rng.random(n) < np.where(seg == 'a', .6, .3)).astype(int),
        'first_order_at': pd.Timestamp('2025-01-01') + pd.to_timedelta(rng.integers(0, 365, n), unit='D'),
    })
    return df


@pytest.fixture(scope='session')
def sandbox_db(tmp_path_factory):
    """A small synthetic platform DuckDB (6 partners, ~1,500 accounts). ~5s once per session."""
    from monaco.sandbox import synth
    from monaco.sandbox.load_sandbox import load, report
    db = tmp_path_factory.mktemp('data') / 'sandbox.duckdb'
    frames = synth.generate(seed=3, n_partners=6, n_accounts=1500, start='2025-06-01', as_of='2026-10-22')
    frames['_mode'] = 'synthetic'
    con = load(frames, db)
    report(con, '2026-10-22')
    con.close()
    os.environ['MONACO_DATA'] = str(db.parent)
    return db
