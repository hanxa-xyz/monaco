"""One command: partner x month table (+ partner x account roll-up) → concentration → early-warning flags → trends → readout.

    monaco-partner-health                                  # sandbox DuckDB + the packaged partner_month.sql / partner_accounts.sql
    monaco-partner-health --csv-month pm.csv --cols-month partner_id=corr,month=ym
    monaco-partner-health --as-of 2026-09-30 --top 8 --min-n 150

Prints every table it charts; writes PNGs + CSVs + readout.md (with the forced close) under --out.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import pandas as pd

from monaco import partner_health as hl
from monaco import readout as ds
from monaco.io import load, parse_cols
from monaco.paths import SQL_DIR, default_db, out_dir
from monaco.stats import pct


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_argument_group('input')
    src.add_argument('--db', default=None, help='DuckDB file (default: $MONACO_DATA/sandbox.duckdb)')
    src.add_argument('--sql-month', default=str(SQL_DIR / 'partner_month.sql'))
    src.add_argument('--sql-accounts', default=str(SQL_DIR / 'partner_accounts.sql'))
    src.add_argument('--csv-month', help='CSV with the partner x month table instead of --db')
    src.add_argument('--csv-accounts', help='CSV with the partner x account roll-up (optional)')
    src.add_argument('--no-accounts', action='store_true', help='skip the account roll-up (no distribution view)')
    src.add_argument('--cols-month', help='partner_id=<col>,month=<col>,...')
    src.add_argument('--cols-accounts', help='account_id=<col>,partner_id=<col>,...')
    ap.add_argument('--as-of', help='data cut date; decides whether the last month is partial (default: assume partial)')
    ap.add_argument('--top', type=int, default=6, help='partners in the trend grid (by accounts) — flagged partners are added')
    ap.add_argument('--min-n', type=int, default=ds.MIN_GROUP_N)
    ap.add_argument('--months', type=int, default=12)
    ap.add_argument('--out', default=None, help='default: $MONACO_OUT/partner_health')
    a = ap.parse_args()

    ds.setup()
    a.db = a.db or str(default_db())
    out = Path(a.out) if a.out else out_dir('partner_health'); figs = out / 'figs'; tabs = out / 'tables'; figs.mkdir(parents=True, exist_ok=True); tabs.mkdir(parents=True, exist_ok=True)

    pm = load(db=a.db, sql=a.sql_month, csv=a.csv_month, cols=parse_cols(a.cols_month))
    pa = None
    if not a.no_accounts:
        try:
            pa = load(db=a.db, sql=a.sql_accounts, csv=a.csv_accounts, cols=parse_cols(a.cols_accounts))
        except Exception as e:                                         # the roll-up is optional; say so and continue
            print(f'[warn] account roll-up unavailable ({e}); skipping the distribution view')
    pm, as_of, last_complete = hl.prepare(pm, a.as_of)
    print(f'partner_month: {len(pm):,} rows · {pm.partner_id.nunique()} partners · {pm.month.min():%Y-%m} → {pm.month.max():%Y-%m} · '
          f'as_of {as_of:%Y-%m-%d} · last complete month {last_complete:%Y-%m}' + (f' · account roll-up {len(pa):,} rows' if pa is not None else ''))
    pm.to_csv(tabs / 'partner_month_prepared.csv', index=False)

    # portfolio month view (the mix guard: pooled numbers next to partner count)
    port = pm[~pm.partial].groupby('month').agg(partners=('partner_id', 'nunique'), new_accounts=('new_accounts', 'sum'), kyc7_k=('kyc7_k', 'sum'), kyc7_n=('kyc7_n', 'sum'),
                                               fund30_k=('fund30_k', 'sum'), fund30_n=('fund30_n', 'sum'), net_deposits=('net_deposits', 'sum'),
                                               trading_accounts=('trading_accounts', 'sum'), fills=('fills', 'sum'), filled_notional=('filled_notional', 'sum')).tail(a.months)
    port['kyc7'] = port.kyc7_k / port.kyc7_n.replace(0, pd.NA); port['fund30'] = port.fund30_k / port.fund30_n.replace(0, pd.NA)
    port['fills_per_trader'] = port.fills / port.trading_accounts.replace(0, pd.NA)
    ds.print_table(f'portfolio by month (complete months, last {a.months})', port[['partners', 'new_accounts', 'kyc7', 'fund30', 'net_deposits', 'trading_accounts', 'fills_per_trader', 'filled_notional']].round(3))
    port.to_csv(tabs / 'portfolio_month.csv')

    # concentration
    conc, hhi, cfigs = hl.concentration(pm, pa, last_complete)
    ds.print_table('partner concentration (lifetime accounts; money/notional = last 3 complete months)',
                   conc.head(15).round(3), 'HHI: ' + ', '.join(f'{k}={v:.3f}' for k, v in hhi.items()) + '  (0.25+ = highly concentrated)')
    conc.to_csv(tabs / 'partner_concentration.csv')
    for name, (fig, table, note) in cfigs.items():
        ds.print_table(f'{name}', table, note)
        p = ds.save_png(fig, figs, name); print(f'[fig] {p}')

    # early-warning flags
    flags = hl.early_warning(pm, last_complete, min_n=a.min_n)
    show = flags.copy()
    if len(show):
        show['latest'] = show.latest.map(lambda v: f'{v:,.3f}' if abs(v) < 10 else f'{v:,.0f}'); show['baseline'] = show.baseline.map(lambda v: f'{v:,.3f}' if abs(v) < 10 else f'{v:,.0f}')
    ds.print_table(f'early-warning flags: {last_complete:%Y-%m} (acute = latest vs prior 3; sustained = last 2 pooled vs prior 3); FLAG needs ≥ {a.min_n} accounts of basis',
                   show.to_string(index=False) if len(show) else '(none)',
                   'move = partner change; net_of_portfolio = partner change minus the portfolio change over the same months (the gate). Drops first.')
    flags.to_csv(tabs / 'early_warning_flags.csv', index=False)

    # trends: top partners by accounts + flagged ones
    top = conc.index[:a.top].tolist()
    drops = flags[flags.status.str.startswith('FLAG') & flags.flag.str.startswith(('drop', 'contraction'))].partner_id.unique().tolist() if len(flags) else []
    grid = (top + [p for p in drops if p not in top])[:10]                       # top partners + partners with a flagged DROP, max 10 rows
    fig, note = hl.trends(pm, grid, last_complete, months=a.months, flags=flags)
    tt = pm[pm.partner_id.isin(grid) & (pm.month > last_complete - pd.DateOffset(months=a.months))][['partner_id', 'month', 'partial'] + hl.TREND_METRICS + ['fund30_n', 'trading_accounts']]
    ds.print_table(f'trend grid data ({len(grid)} partners × {hl.TREND_METRICS})', tt.round(3).to_string(index=False), note)
    tt.to_csv(tabs / 'trend_grid.csv', index=False)
    p = ds.save_png(fig, figs, 'partner_trends'); print(f'[fig] {p}')

    # readout with the forced close
    real = flags[flags.status.str.startswith('FLAG')] if len(flags) else flags
    top_share = conc.share_accounts.iloc[0]; top_pid = conc.index[0]
    n50 = int(cfigs['pareto_notional'][1].loc[50, 'entities_needed']); n80 = int(cfigs['pareto_notional'][1].loc[80, 'entities_needed'])
    moves = real[real.flag != 'concentration'] if len(real) else real
    lead = moves.iloc[0] if len(moves) else None                                  # drops sort first, then by size net of portfolio
    headline = (f'{last_complete:%b %Y}: {len(moves)} flags across {moves.partner_id.nunique() if len(moves) else 0} partners '
                f'({int(moves.flag.str.startswith(("drop", "contraction")).sum()) if len(moves) else 0} drops); '
                f'{top_pid} holds {pct(top_share)} of accounts; {n50} partners make 50% and {n80} make 80% of filled notional. '
                + (f'Lead: {lead.partner_id} {lead.metric} {lead.flag} ({lead.test}, {lead.net_of_portfolio or lead.move or "n/a"} net of portfolio).' if lead is not None else 'No partner outside its band.'))
    sections = [
        ('Inputs', f'- grain: partner × calendar month (cohort rates keyed by creation month, flows by event month); live accounts only\n'
                   f'- {pm.partner_id.nunique()} partners, {pm.month.min():%Y-%m} → {pm.month.max():%Y-%m}; as_of {as_of:%Y-%m-%d}; last complete month {last_complete:%Y-%m}\n'
                   f'- flag rule: outside the baseline 95% band AND move net of the portfolio ≥ 5 pp (rates) / ≥ 20% (counts, dollars, ratios) AND ≥ {a.min_n} accounts of basis; acute (latest vs prior 3) and sustained (last 2 vs prior 3); contraction = 2 months net deposits < 0; concentration ≥ 25% share'),
        ('Portfolio by month', port[['partners', 'new_accounts', 'kyc7', 'fund30', 'net_deposits', 'trading_accounts', 'fills_per_trader', 'filled_notional']].round(3)),
        ('Concentration (top 15)', conc.head(15).round(3)),
        ('Early-warning flags', flags.round(3) if len(flags) else '(none)'),
        ('Figures', '\n'.join(f'- figs/{p.name}' for p in sorted(figs.glob('*.png')))),
    ]
    close = {'headline': headline,
             'decision': '[draft] Investigate / hold: flags are statistical, not diagnoses. Name which flagged partner moves the portfolio number and which is a small partner being noisy.',
             'action': (f'[draft] For {lead.partner_id}: split {lead.metric} by creation cohort and KYC path this week; ask the partner manager what changed in {last_complete:%b}.' if lead is not None
                        else '[draft] No action; keep the monthly run.'),
             'guardrail': f'[draft] Portfolio fund30 and net deposits excluding {top_pid}; if they move with {top_pid}, it is the mix, not the partner.',
             'revisit': f'[draft] Re-run after {(last_complete + pd.DateOffset(months=1)):%b %Y} closes; a flag that persists two months becomes an escalation.'}
    r = ds.write_readout(out / 'readout.md', f'Partner health readout — {last_complete:%Y-%m}', sections, close)
    print(f'\n[readout] {r}\n' + ds.CLOSE_TEMPLATE.format(**close))


if __name__ == '__main__':
    main()
