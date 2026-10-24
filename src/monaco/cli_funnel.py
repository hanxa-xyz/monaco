"""One command: event table → stage table → conversion by partner and cohort → time-to-stage → retention → readout.

    monaco-funnel                                   # sandbox DuckDB ($MONACO_DATA) + the packaged funnel_events.sql
    monaco-funnel --csv events.csv --cols account_id=acct,partner_id=corr,event=stage,ts=event_time
    monaco-funnel --window 7 --top 12 --out out/funnel_7d

Prints every table it charts; writes PNGs + CSVs + readout.md (with the forced close) under --out.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import pandas as pd

from monaco import funnel as fn
from monaco import readout as ds
from monaco.io import load, parse_cols
from monaco.paths import SQL_DIR, default_db, out_dir
from monaco.stats import pct


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_argument_group('input (contract: account_id, partner_id, event, ts)')
    src.add_argument('--db', default=None, help='DuckDB file (default: $MONACO_DATA/sandbox.duckdb)')
    src.add_argument('--sql', default=str(SQL_DIR / 'funnel_events.sql'), help='SQL file or text producing the event table')
    src.add_argument('--csv', help='CSV with the event table instead of --db/--sql')
    src.add_argument('--parquet', help='Parquet with the event table instead of --db/--sql')
    src.add_argument('--cols', help='map input columns onto the contract: account_id=<col>,partner_id=<col>,event=<col>,ts=<col>')
    ap.add_argument('--stages', default=','.join(fn.DEFAULT_STAGES), help='ordered stage event names; the last may be first_<activity>')
    ap.add_argument('--activity', default='trade', help='repeated activity event used for first_<activity> and retention')
    ap.add_argument('--window', type=int, default=30, help='days from the first stage for conversion rates')
    ap.add_argument('--as-of', help='censoring date (default: max ts in the data)')
    ap.add_argument('--top', type=int, default=10, help='partners shown in charts (tables show all with n ≥ --min-n)')
    ap.add_argument('--min-n', type=int, default=ds.MIN_GROUP_N)
    ap.add_argument('--max-age', type=int, default=12, help='retention ages (months)')
    ap.add_argument('--retention-age', type=int, default=3, help='age used for the by-partner retention view')
    ap.add_argument('--out', default=None, help='default: $MONACO_OUT/funnel')
    a = ap.parse_args()

    ds.setup()
    a.db = a.db or str(default_db())
    out = Path(a.out) if a.out else out_dir('funnel'); figs = out / 'figs'; tabs = out / 'tables'; figs.mkdir(parents=True, exist_ok=True); tabs.mkdir(parents=True, exist_ok=True)
    stages = [s.strip() for s in a.stages.split(',')]

    ev = load(db=a.db, sql=a.sql, csv=a.csv, parquet=a.parquet, cols=parse_cols(a.cols))
    ev, stages = fn.prepare(ev, stages, a.activity)
    as_of = pd.Timestamp(a.as_of) if a.as_of else ev.ts.max()
    print(f'events: {len(ev):,} rows · {ev.account_id.nunique():,} accounts · {ev.partner_id.nunique()} partners · '
          f'{ev.ts.min():%Y-%m-%d} → {ev.ts.max():%Y-%m-%d} · as_of {as_of:%Y-%m-%d} · stages {stages} · window {a.window}d')
    ds.print_table('event counts', ev.event.value_counts().to_frame('rows'))

    st = fn.stage_table(ev, stages)
    skew = sum(int(((st[b] < st[a_]) & st[b].notna()).sum()) for a_, b in zip(stages[:-1], stages[1:]))
    ds.print_table('stage table (one row per account; first ts per stage)', st.head(8).to_string(index=False),
                   f'{len(st):,} accounts; {skew:,} stage pairs out of order (clock skew / backfill) kept as-is')
    st.to_csv(tabs / 'stage_table.csv', index=False)

    # conversion by partner
    conv_p, summ_p, flagged = fn.conversion(st, stages, 'partner_id', a.window, as_of, a.min_n)
    show = [c for c in conv_p.columns if c.startswith(('n', 'k_', 'rate_', 'cond_'))]
    ds.print_table(f'{a.window}-day conversion by partner (rate OF ACCOUNTS CREATED, accounts old enough for the window)',
                   pd.concat([conv_p[show], summ_p.reindex(columns=show)]).round(4))
    conv_p.to_csv(tabs / f'conversion_by_partner_{a.window}d.csv'); summ_p.to_csv(tabs / f'conversion_summary_{a.window}d.csv')
    fig, note = fn.funnel_panels(conv_p, stages, a.window, top=a.top, min_n=a.min_n, pooled=summ_p)
    p = ds.save_png(fig, figs, f'funnel_by_partner_{a.window}d'); print(note); print(f'[fig] {p}')

    # conversion by cohort month
    conv_c, summ_c, _ = fn.conversion(st, stages, 'cohort_month', a.window, as_of, a.min_n)
    conv_c = conv_c.sort_index()
    ds.print_table(f'{a.window}-day conversion by creation cohort month', conv_c[show].round(4))
    conv_c.to_csv(tabs / f'conversion_by_cohort_{a.window}d.csv')
    fig, note = fn.cohort_lines(conv_c, stages, a.window)
    p = ds.save_png(fig, figs, f'conversion_by_cohort_{a.window}d'); print(note); print(f'[fig] {p}')

    # time to stage
    fig, tts, note = fn.time_to_stage(st, stages, as_of)
    ds.print_table('time to stage (days; percentiles among arrivers; never_arrived as of as_of)', tts, note)
    tts.to_csv(tabs / 'time_to_stage.csv')
    p = ds.save_png(fig, figs, 'time_to_stage'); print(f'[fig] {p}')

    # retention
    anchor = stages[-2] if len(stages) >= 2 else stages[0]
    fig, tri, pooled, note = fn.retention(ev, st, as_of, anchor=anchor, activity_event=a.activity, max_age=a.max_age)
    ds.print_table(f'retention triangle: {anchor} cohort × age (share with ≥1 {a.activity}); NaN = age not complete', tri, note)
    ds.print_table('pooled retention by age', pooled.to_frame('active_rate').T)
    tri.to_csv(tabs / 'retention_triangle.csv'); pooled.to_csv(tabs / 'retention_pooled.csv')
    p = ds.save_png(fig, figs, 'retention_curves'); print(f'[fig] {p}')

    fig, rbp, note, _ = fn.retention_by_partner(ev, st, as_of, age=a.retention_age, anchor=anchor, activity_event=a.activity, top_k=a.top)
    ds.print_table(f'active at M{a.retention_age} by partner (penetration view)', rbp, note)
    rbp.to_csv(tabs / f'retention_m{a.retention_age}_by_partner.csv')
    p = ds.save_png(fig, figs, f'retention_m{a.retention_age}_by_partner'); print(f'[fig] {p}')

    # readout with the forced close
    last = stages[-1]; pooled_rate = summ_p.loc['POOLED (account-weighted)', f'rate_{last}']
    pw_rows = [i for i in summ_p.index if i.startswith('PARTNER-WEIGHTED')]
    pw_rate = summ_p.loc[pw_rows[0], f'rate_{last}'] if pw_rows else float('nan')
    big = conv_p[conv_p.n >= a.min_n]
    worst = big[f'rate_{last}'].idxmin() if len(big) else None
    m3 = pooled.get(a.retention_age, float('nan'))
    headline = (f'{pct(pooled_rate)} of accounts created reach {last.replace("_", " ")} within {a.window} days (pooled); '
                f'{pct(pw_rate)} partner-weighted. Lowest big partner: {worst} at {pct(big.loc[worst, f"rate_{last}"]) if worst else "—"}. '
                f'M{a.retention_age} retention after {anchor}: {pct(m3)}.')
    sections = [
        ('Inputs', f'- grain: one row per account (not per human); live accounts only\n- events: {len(ev):,} rows, {ev.account_id.nunique():,} accounts, '
                   f'{ev.partner_id.nunique()} partners, as_of {as_of:%Y-%m-%d}\n- stages: {" → ".join(stages)}; window {a.window} days from {stages[0]}; '
                   f'denominators hold only accounts old enough for the window\n- source: {a.csv or a.parquet or (a.db + " + " + a.sql)}'),
        (f'{a.window}-day conversion by partner (top {a.top} + summary rows)', pd.concat([conv_p[show].head(a.top), summ_p.reindex(columns=show)]).round(3)),
        ('Conversion by cohort month', conv_c[show].round(3)),
        ('Time to stage', tts),
        ('Retention triangle', tri),
        (f'Active at M{a.retention_age} by partner', rbp),
        ('Figures', '\n'.join(f'- figs/{p.name}' for p in sorted(figs.glob('*.png')))),
    ]
    close = {'headline': headline,
             'decision': '[draft] No decision from a descriptive funnel alone: name the stage with the largest partner-weighted gap and whether it is mix or product.',
             'action': f'[draft] Split the weakest stage for {worst} by cohort month and KYC path; agree the funded definition (ACH COMPLETE vs JNLC) with the partner team.',
             'guardrail': f'[draft] Account-weighted vs partner-weighted {last.replace("_", " ")} rate must move together; a gap > 5 pts means a mix shift, not a product change.',
             'revisit': f'[draft] Re-run when the newest cohort has {a.window} days of age; retention at M{a.retention_age} needs cohorts through {(as_of.to_period("M") - a.retention_age - 1)}.'}
    r = ds.write_readout(out / 'readout.md', f'Account funnel readout — {as_of:%Y-%m-%d}', sections, close)
    print(f'\n[readout] {r}\n' + ds.CLOSE_TEMPLATE.format(**close))


if __name__ == '__main__':
    main()
