"""One command: unit × period panel → 2x2 DiD with cluster-bootstrap SE → event study + pre-trend test → readout.

    monaco-did                                                    # sandbox: KYC-approval rate, treated partner vs the rest
    monaco-did --csv panel.csv --cols unit=geo,period=week,y=conversions --treated-units NYC,BOS --treat-period 2026-03-02
    monaco-did --y fund30 --treated-units CNTR --treat-period 2026-08-01

The sandbox default recovers a planted effect: one partner's KYC approval rate drops ~25 pts from a known month.
Prints every table it charts; writes PNGs + CSVs + readout.md (with the forced close) under --out.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import numpy as np
import pandas as pd

from monaco import causal as cz
from monaco import readout as ds
from monaco.io import load, parse_cols
from monaco.paths import SQL_DIR, default_db, out_dir

SANDBOX_RATES = {'kyc7': ('kyc7_k', 'kyc7_n', 'KYC approved ≤7d (rate)'), 'fund30': ('fund30_k', 'fund30_n', 'funded ≤30d (rate)')}


def sandbox_panel(db, sql, y):
    pm = load(db=db, sql=sql)
    pm['month'] = pd.to_datetime(pm['month'])
    if y in SANDBOX_RATES:
        k, n, label = SANDBOX_RATES[y]
        pm = pm[pm[n] > 0].copy(); pm[y] = pm[k] / pm[n]
    else:
        label = y
    return pm.rename(columns={'partner_id': 'unit', 'month': 'period'})[['unit', 'period', y]], label


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_argument_group('input (contract: unit, period, y)')
    src.add_argument('--db', default=None, help='DuckDB file (default: $MONACO_DATA/sandbox.duckdb)')
    src.add_argument('--sql', default=str(SQL_DIR / 'partner_month.sql'))
    src.add_argument('--csv', help='CSV panel instead of --db')
    src.add_argument('--cols', help='unit=<col>,period=<col>,y=<col>')
    ap.add_argument('--y', default='kyc7', help='outcome column (sandbox: kyc7 | fund30 | any partner_month column)')
    ap.add_argument('--treated-units', default='KYCD', help='comma-separated unit ids that received the treatment')
    ap.add_argument('--treat-period', default='2026-08-01', help='first treated period (same type as the period column)')
    ap.add_argument('--window', default='-6,4', help='event-study window in periods relative to treatment')
    ap.add_argument('--drop-partial', action='store_true', default=True, help='drop the last period if it looks partial (default on)')
    ap.add_argument('--n-boot', type=int, default=500)
    ap.add_argument('--out', default=None, help='default: $MONACO_OUT/did')
    a = ap.parse_args()

    ds.setup()
    out = Path(a.out) if a.out else out_dir('did'); figs = out / 'figs'; tabs = out / 'tables'
    figs.mkdir(parents=True, exist_ok=True); tabs.mkdir(parents=True, exist_ok=True)
    if a.csv:
        panel = load(csv=a.csv, cols=parse_cols(a.cols)); label = a.y; src_desc = a.csv
        if 'y' in panel.columns and a.y not in panel.columns:
            panel = panel.rename(columns={'y': a.y})
    else:
        db = a.db or str(default_db()); panel, label = sandbox_panel(db, a.sql, a.y); src_desc = f'{db} + {a.sql}'
    y = a.y
    # period typing
    try:
        panel['period'] = pd.to_datetime(panel['period']); tp = pd.Timestamp(a.treat_period)
    except (ValueError, TypeError):
        tp = type(panel['period'].iloc[0])(a.treat_period)
    if a.drop_partial and not a.csv:
        panel = panel[panel.period < panel.period.max()]           # sandbox: the last month is partial
    treated_units = [u.strip() for u in a.treated_units.split(',')]
    panel['treated'] = panel.unit.isin(treated_units).astype(int)
    panel['post'] = (panel.period >= tp).astype(int)
    lo_w, hi_w = (int(v) for v in a.window.split(','))

    print(f'panel: {len(panel):,} unit-periods · {panel.unit.nunique()} units ({panel.treated.groupby(panel.unit).max().sum()} treated) · '
          f'{panel.period.nunique()} periods · treatment from {tp:%Y-%m-%d} · outcome = {label}')
    panel.to_csv(tabs / 'panel.csv', index=False)

    res = cz.did(panel, 'unit', 'period', y, 'treated', 'post', n_boot=a.n_boot)
    ds.print_table('2x2 cell means (unit-period rows, unweighted)', res['cells'].round(4),
                   f'ATT = {res["att"]:+.4f}  SE {res["se"]:.4f}  95% CI [{res["lo"]:+.4f}, {res["hi"]:+.4f}]  p = {res["p"]:.3g}  '
                   f'(cluster bootstrap over {res["n_treated_units"]} treated + {res["n_control_units"]} control units, B = {res["n_boot"]})'
                   + (f'\n[caveat] {res["caveat"]}' if res.get('caveat') else ''))
    res['cells'].to_csv(tabs / 'did_cells.csv')
    fig, note = cz.plot_did(panel, 'period', y, 'treated', tp, res, y_label=label, fmt=lambda v: f'{v:+.3f}')
    p = ds.save_png(fig, figs, 'did'); print(note); print(f'[fig] {p}')

    es, pre = cz.event_study(panel, 'unit', 'period', y, 'treated', tp, window=(lo_w, hi_w), n_boot=max(200, a.n_boot // 2))
    ds.print_table('event study (coef = gap vs control, relative to period −1)', es.round(4),
                   f'pre-trend joint test: chi2 = {pre["chi2"]:.2f}, df = {pre["df"]}, p = {pre["p"]:.2f}; max |pre coef| = {pre["max_abs_pre"]:.4f}')
    es.to_csv(tabs / 'event_study.csv')
    fig, note = cz.plot_event_study(es, pre, y_label=f'effect on {label}')
    p = ds.save_png(fig, figs, 'event_study'); print(note); print(f'[fig] {p}')

    ladder, ltab = cz.method_ladder(panel_pre_post=True)
    ds.print_table('where this sits on the ladder', ltab)

    post_coefs = es[es.index >= 0].coef
    headline = (f'DiD ATT on {label}: {res["att"]:+.3f} [{res["lo"]:+.3f}, {res["hi"]:+.3f}] for {", ".join(treated_units)} from {tp:%b %Y}, '
                f'vs {res["n_control_units"]} control units. Pre-trend test p = {pre["p"]:.2f}; post effects range {post_coefs.min():+.3f} to {post_coefs.max():+.3f}.')
    sections = [
        ('Inputs', f'- grain: one row per unit × period; treated = {treated_units}; post = period ≥ {tp:%Y-%m-%d}\n- source: {src_desc}\n'
                   f'- SE: cluster bootstrap over units (B = {res["n_boot"]}); periods in event study: {lo_w}..{hi_w}\n'
                   + (f'- caveat: {res["caveat"]}\n' if res.get('caveat') else '') +
                   f'- assumption to defend: {ladder["assumption"]}; main pitfall: {ladder["pitfall"]}'),
        ('2x2 cells', res['cells'].round(4)),
        ('Event study', es.round(4)),
        ('Figures', '\n'.join(f'- figs/{p.name}' for p in sorted(figs.glob('*.png')))),
    ]
    sig = res['p'] < 0.05 if np.isfinite(res['p']) else False
    # parallel trends: the joint test (overpowered when one arm is a single unit) OR a magnitude rule — pre coefs small vs the effect
    pt_ok = (pre['p'] > 0.10) or (abs(res['att']) > 0 and pre['max_abs_pre'] < 0.25 * abs(res['att']))
    pt_txt = (f'pre coefficients within ±{pre["max_abs_pre"]:.3f} of zero vs an effect of {res["att"]:+.3f} (joint test p = {pre["p"]:.2f})')
    close = {'headline': headline,
             'decision': f'[draft] {"Effect is distinguishable from zero" if sig else "Effect is not distinguishable from zero"}; parallel trends '
                         f'{"look supported" if pt_ok else "are NOT supported"}: {pt_txt}. State whether the control units are a credible counterfactual before acting.',
             'action': f'[draft] If acting: scope to the treated units from {tp:%b %Y}; if pre-trends fail, re-pick controls (matched on pre-period level and slope) or move down the ladder.',
             'guardrail': '[draft] Composition of treated units (new vs existing entities) stable across the window; a post-period mix shift masquerades as an effect.',
             'revisit': '[draft] Re-run with one more post period; if more units adopt later, switch to a staggered estimator before pooling them.'}
    rpath = ds.write_readout(out / 'readout.md', f'DiD readout — {label}', sections, close)
    print(f'\n[readout] {rpath}\n' + ds.render_close(close))


if __name__ == '__main__':
    main()
