import pytest

from monaco import partner_health as hl
from monaco.io import load
from monaco.paths import SQL_DIR


@pytest.fixture(scope='module')
def pm(sandbox_db):
    df = load(db=sandbox_db, sql=SQL_DIR / 'partner_month.sql')
    missing = set(hl.REQUIRED) - set(df.columns)
    assert not missing, missing
    return df


@pytest.fixture(scope='module')
def pa(sandbox_db):
    return load(db=sandbox_db, sql=SQL_DIR / 'partner_accounts.sql')


def test_prepare_marks_partial_month(pm):
    d, as_of, last_complete = hl.prepare(pm, '2026-10-22')
    assert 'partial' in d.columns and d.partial.any()
    assert last_complete.strftime('%Y-%m') == '2026-09'


def test_concentration_shares_and_hhi(pm, pa):
    d, _, last_complete = hl.prepare(pm, '2026-10-22')
    tab, hhi, figs = hl.concentration(d, pa, last_complete)
    vals = list(hhi.values()) if isinstance(hhi, dict) else [hhi]
    assert vals and all(0 < v <= 1 for v in vals), hhi
    share_cols = [c for c in tab.columns if 'share' in c]
    assert share_cols
    assert abs(tab[share_cols[0]].sum() - 1) < 1e-6


def test_early_warning_flags_are_statistical_not_guesses(pm):
    d, _, last_complete = hl.prepare(pm, '2026-10-22')
    out = hl.early_warning(d, last_complete, min_n=20)
    assert {'partner_id', 'metric', 'flag', 'latest', 'baseline', 'status'} <= set(out.columns)
    flagged = out[out.status == 'FLAG']
    # a flag must come with a baseline and a move; thin partners are never flagged
    assert flagged.baseline.notna().all()
    assert (flagged.basis_accounts >= 20).all()


def test_trends_grid_runs(pm):
    d, _, last_complete = hl.prepare(pm, '2026-10-22')
    partners = d.groupby('partner_id').new_accounts.sum().nlargest(3).index.tolist()
    fig, note = hl.trends(d, partners, last_complete, months=6)
    assert fig is not None and note
