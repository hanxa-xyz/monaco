"""One command: (start, end, as_of) rows → KM curve + CI + at-risk → by-group curves + log-rank → naive-vs-KM → readout.

    monaco-survival                                   # sandbox: funded → first trade, grouped by partner
    monaco-survival --csv subs.csv --cols entity_id=user_id,group=plan,start=subscribed_at,end=churned_at --unit D --marks 30,90,180
    monaco-survival --duration-csv d.csv             # already (duration, event[, group])

Prints every table it charts; writes PNGs + CSVs + readout.md (with the forced close) under --out.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import numpy as np
import pandas as pd

from monaco import funnel as fn
from monaco import readout as ds
from monaco import survival as sv
from monaco.io import load, parse_cols
from monaco.paths import SQL_DIR, default_db, out_dir
from monaco.stats import pct


def sandbox_frame(db, sql):
    """Funded accounts: t0 = funded, event = first trade (FILL), censored at the data's as_of; group = partner."""
    ev = load(db=db, sql=sql)
    ev, stages = fn.prepare(ev)
    st = fn.stage_table(ev, stages)
    st = st[st['funded'].notna()]
    return pd.DataFrame({'entity_id': st.account_id, 'group': st.partner_id, 'start': st['funded'], 'end': st['first_trade']}), ev.ts.max()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_argument_group('input (contract: entity_id, group, start, end  — or duration, event[, group])')
    src.add_argument('--db', default=None, help='DuckDB file (default: $MONACO_DATA/sandbox.duckdb)')
    src.add_argument('--sql', default=str(SQL_DIR / 'funnel_events.sql'))
    src.add_argument('--csv', help='CSV with start/end timestamps')
    src.add_argument('--duration-csv', help='CSV already in duration/event[/group] form')
    src.add_argument('--cols', help='map input columns: entity_id=<col>,group=<col>,start=<col>,end=<col> (or duration=,event=,group=)')
    ap.add_argument('--as-of', help='censoring date (default: max timestamp in the data)')
    ap.add_argument('--unit', default='D', help='pandas offset unit for durations: D, W, h')
    ap.add_argument('--marks', default='1,7,30', help='times to report S(t) at')
    ap.add_argument('--xmax', type=float, default=None, help='x-axis limit for the curves (default: 1.15 × last mark)')
    ap.add_argument('--tau', type=float, default=None, help='RMST horizon (default: last mark)')
    ap.add_argument('--top', type=int, default=5, help='groups drawn (largest by n); all with n ≥ --min-n are in the tables')
    ap.add_argument('--min-n', type=int, default=sv.MIN_GROUP)
    ap.add_argument('--label', default='funded → first trade', help='what t0 and the event are, for titles')
    ap.add_argument('--out', default=None, help='default: $MONACO_OUT/survival')
    a = ap.parse_args()

    ds.setup()
    out = Path(a.out) if a.out else out_dir('survival'); figs = out / 'figs'; tabs = out / 'tables'
    figs.mkdir(parents=True, exist_ok=True); tabs.mkdir(parents=True, exist_ok=True)
    marks = [float(m) for m in a.marks.split(',')]; tau = a.tau or marks[-1]; xmax = a.xmax or marks[-1] * 1.15
    cols = parse_cols(a.cols)

    if a.duration_csv:
        d = load(csv=a.duration_csv, cols=cols); src_desc = a.duration_csv; as_of = None
        d.attrs['note'] = f'{len(d):,} rows; {int(d.event.sum()):,} events, {int((1 - d.event).sum()):,} censored'
    else:
        if a.csv:
            raw = load(csv=a.csv, cols=cols); src_desc = a.csv; data_as_of = None
        else:
            db = a.db or str(default_db()); raw, data_as_of = sandbox_frame(db, a.sql); src_desc = f'{db} + {a.sql}'
        as_of = a.as_of or data_as_of
        d = sv.from_timestamps(raw, 'start', 'end', as_of=as_of, group='group' if 'group' in raw else None, unit=a.unit, entity='entity_id' if 'entity_id' in raw else None)
    unit_label = {'D': 'days', 'W': 'weeks', 'h': 'hours'}.get(a.unit, a.unit)
    print(f'{a.label}: {d.attrs.get("note", "")}')
    d.to_csv(tabs / 'durations.csv', index=False)

    # pooled curve
    pooled = sv.km(d.duration, d.event)
    s_at = sv.survival_at(pooled, marks); med = sv.median_survival(pooled); r = sv.rmst(pooled, tau)
    hz = sv.hazard_window(pooled, width=max(1.0, marks[0]))
    ds.print_table(f'KM (pooled): S at marks ({unit_label})', s_at.round(4))
    ds.print_table('KM table (first 12 event times)', pooled.head(12).round(4),
                   f'median = {med:,.1f} {unit_label}' + (' (not reached)' if not np.isfinite(med) else '') + f'; RMST to {tau:g} = {r:,.1f} {unit_label}; '
                   f'peak-hazard window = {hz[0]:g}–{hz[1]:g} {unit_label} (drop {pct(hz[2])})')
    pooled.to_csv(tabs / 'km_pooled.csv', index=False); s_at.to_csv(tabs / 'survival_at_marks.csv', index=False)
    fig, note = sv.plot_km({'all': pooled}, marks, unit_label, title=f'Time to event: {a.label}', xmax=xmax)
    p = ds.save_png(fig, figs, 'km_pooled'); print(note); print(f'[fig] {p}')

    # naive vs km
    cmp = sv.naive_vs_km(d, marks)
    ds.print_table('naive cohort read vs KM at the marks', cmp.round(4))
    cmp.to_csv(tabs / 'naive_vs_km.csv', index=False)
    fig, note = sv.plot_naive_vs_km(cmp, unit_label); p = ds.save_png(fig, figs, 'naive_vs_km'); print(note); print(f'[fig] {p}')

    # by group
    lr = None; by = None
    if 'group' in d.columns:
        sizes = d.group.value_counts(); big = sizes[sizes >= a.min_n]
        rows = []
        curves = {'all': pooled}
        for g in big.index:
            dg = d[d.group == g]; kg = sv.km(dg.duration, dg.event)
            sa = sv.survival_at(kg, marks)
            rows.append([g, len(dg), int(dg.event.sum())] + list(sa.S.round(4)) + [sv.median_survival(kg), sv.rmst(kg, tau)])
            if len(curves) - 1 < a.top:
                curves[g] = kg
        by = pd.DataFrame(rows, columns=['group', 'n', 'events'] + [f'S_{m:g}' for m in marks] + ['median', f'rmst_{tau:g}']).set_index('group')
        ds.print_table(f'by group (n ≥ {a.min_n}); S at marks, median, RMST', by.round(3))
        by.to_csv(tabs / 'by_group.csv')
        if len(big) >= 2:
            chi2, dof, pval, lrt = sv.logrank(d[d.group.isin(big.index)])
            lr = dict(chi2=chi2, df=dof, p=pval)
            ds.print_table(f'log-rank across {len(big)} groups: chi2 = {chi2:,.1f}, df = {dof}, p = {pval:.2g}', lrt)
            lrt.to_csv(tabs / 'logrank.csv')
        fig, note = sv.plot_km(curves, marks, unit_label, title=f'Time to event by group: {a.label}',
                               subtitle=f'black = all; top {a.top} groups by n; band = 95% CI; groups with n < {a.min_n} omitted', xmax=xmax)
        p = ds.save_png(fig, figs, 'km_by_group'); print(note); print(f'[fig] {p}')

    # readout
    m1 = s_at.iloc[0]; mL = s_at.iloc[-1]
    headline = (f'{pct(1 - mL.S)} of entities reach the event within {mL.t:g} {unit_label} ({pct(1 - m1.S)} within {m1.t:g}); '
                f'median {"not reached" if not np.isfinite(med) else f"{med:,.0f} {unit_label}"}; '
                f'{int((1 - d.event).sum()):,} of {len(d):,} censored, so the naive read is off by {100*(cmp.naive_known_status_only.iloc[-1] - cmp.km_S.iloc[-1]):+.0f} pp at {mL.t:g} {unit_label}.')
    if by is not None and len(by) >= 2:
        worst = by[f'S_{marks[-1]:g}'].idxmax(); best = by[f'S_{marks[-1]:g}'].idxmin()
        headline += f' Slowest group: {worst} ({pct(1 - by.loc[worst, f"S_{marks[-1]:g}"])} by {marks[-1]:g}); fastest: {best}.'
    sections = [
        ('Inputs', f'- grain: one row per entity; t0 = {a.label.split("→")[0].strip()}, event = {a.label.split("→")[-1].strip()}; censored at as_of\n'
                   f'- {d.attrs.get("note", "")}\n- source: {src_desc}\n- assumption said once: censoring is non-informative (being recent does not predict the event)'),
        ('S(t) at the marks', s_at.round(4)),
        ('Naive vs KM', cmp.round(4)),
    ]
    if by is not None:
        sections.append(('By group', by.round(3)))
    if lr:
        sections.append(('Log-rank', f'chi2 = {lr["chi2"]:,.1f}, df = {lr["df"]}, p = {lr["p"]:.2g} — curves differ; this is association, groups self-select'))
    sections.append(('Figures', '\n'.join(f'- figs/{p.name}' for p in sorted(figs.glob('*.png')))))
    close = {'headline': headline,
             'decision': '[draft] Descriptive: hold. Name whether the peak-hazard window (' + f'{hz[0]:g}–{hz[1]:g} {unit_label}' + ') is where an intervention could land.',
             'action': f'[draft] Target the {hz[0]:g}–{hz[1]:g} {unit_label} window; if groups differ, pick one slow group and check its composition before reading it as a product gap.',
             'guardrail': '[draft] Share censored by cohort month; if the newest cohorts dominate the tail, the curve is a maturity artefact, not a change.',
             'revisit': f'[draft] Re-run when the newest cohort has {marks[-1]:g} {unit_label} of age; add Cox PH for covariates, then a holdout for causation.'}
    rpath = ds.write_readout(out / 'readout.md', f'Survival readout — {a.label}', sections, close)
    print(f'\n[readout] {rpath}\n' + ds.render_close(close))


if __name__ == '__main__':
    main()
