"""funnel — account-funnel analytics on a schema-agnostic event table (account_id, partner_id, event, ts).

Views (all return (fig | None, table, note); every table is printed by run.py):
    stage_table        one row per account: first ts per stage, cohort_month, partner_id
    conversion         W-day stage conversion by group (partner_id or cohort_month) with Wilson CIs,
                       censoring-aware denominators, pooled vs partner-weighted rows
    funnel_panels      the by-partner chart: HORIZONTAL bars, one panel per stage, shared row order
    cohort_lines       conversion by cohort month, one line per stage, CI band on the last stage
    time_to_stage      step CDFs of days between consecutive stages, p50/p75/p90 + never-reached share
    retention          funded-cohort x age triangle (monthly active = ≥1 trade in month k) + quarterly curves
    retention_by_partner  penetration view (eda_views) of 'active at age k' by partner

Composes monaco.eda where a view already exists (penetration, pareto); builds only what the
vocabulary lacks (multi-panel funnel, cohort lines, CDFs, retention curves) in the same grammar.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from monaco import eda as eda_views
from monaco import readout as ds
from monaco import viz as dsviz
from monaco.stats import pct, wilson

BLACK, O_DARK, O_MID, O_LIGHT, O_PALE, GRAY = dsviz.BLACK, dsviz.O_DARK, dsviz.O_MID, dsviz.O_LIGHT, dsviz.O_PALE, dsviz.GRAY
DEFAULT_STAGES = ['created', 'kyc_approved', 'funded', 'first_trade']
RAMP = [O_LIGHT, O_MID, O_DARK, BLACK]


# ------------------------------------------------------------------ 0 shape
def prepare(ev, stages=DEFAULT_STAGES, activity_event='trade'):
    """Validate the contract, parse ts, derive first_<activity> if the stage is missing but repeated activity
    events exist. Returns (events, stages)."""
    need = {'account_id', 'partner_id', 'event', 'ts'}
    missing = need - set(ev.columns)
    if missing:
        raise SystemExit(f'event table is missing columns {sorted(missing)}; map them with --cols')
    ev = ev.copy(); ev['ts'] = pd.to_datetime(ev['ts']); ev['event'] = ev['event'].astype(str)
    ev = ev.dropna(subset=['ts'])
    present = set(ev.event.unique())
    last = stages[-1]
    if last not in present and last.startswith('first_') and last[6:] in present:
        f = ev[ev.event == last[6:]].groupby(['account_id', 'partner_id'], as_index=False).ts.min().assign(event=last)
        ev = pd.concat([ev, f[ev.columns]], ignore_index=True)
    absent = [s for s in stages if s not in set(ev.event.unique())]
    if absent:
        raise SystemExit(f'stages {absent} never occur in the event table (events present: {sorted(present)[:12]})')
    return ev, stages


def stage_table(ev, stages):
    """One row per account, first timestamp per stage (MIN collapses retries), cohort_month from the first stage."""
    st = ev[ev.event.isin(stages)].pivot_table(index=['account_id', 'partner_id'], columns='event', values='ts', aggfunc='min')
    st = st.reindex(columns=stages).reset_index()
    st = st[st[stages[0]].notna()].copy()
    st['cohort_month'] = st[stages[0]].dt.to_period('M').dt.to_timestamp()
    # enforce monotone order: a stage reached "before" the previous one is clock skew; keep it but note it
    return st.sort_values(stages[0]).reset_index(drop=True)


# ------------------------------------------------------------------ 1 conversion
def flags(st, stages, window_days, as_of):
    """Add reached_<stage> (0/1 within window of the first stage) and eligible (old enough for the window)."""
    d = st.copy(); t0 = d[stages[0]]
    d['eligible'] = (t0 <= as_of - pd.Timedelta(days=window_days)) if window_days else True
    for s in stages[1:]:
        hit = d[s].notna() & ((d[s] - t0) <= pd.Timedelta(days=window_days)) if window_days else d[s].notna()
        d[f'reached_{s}'] = hit.astype(int)
    return d


def conversion(st, stages, by, window_days, as_of, min_n=ds.MIN_GROUP_N, top=None):
    """Rates OF ACCOUNTS CREATED (eligible for the window), by `by`; pooled + partner-weighted summary rows.
    Columns per stage: k, rate, lo, hi; cond_<stage> = step-conditional rate."""
    d = flags(st, stages, window_days, as_of)
    d = d[d.eligible]
    g = d.groupby(by)
    out = pd.DataFrame({'n': g.size()})
    prev = None
    for s in stages[1:]:
        k = g[f'reached_{s}'].sum(); r, lo, hi = wilson(k, out.n)
        out[f'k_{s}'] = k; out[f'rate_{s}'] = r; out[f'lo_{s}'] = lo; out[f'hi_{s}'] = hi
        out[f'cond_{s}'] = r if prev is None else (k / out[f'k_{prev}'].replace(0, np.nan)).values
        prev = s
    out = out.sort_values('n', ascending=False)
    if top:
        out = out.head(top)
    # summary rows
    pooled = {'n': len(d)}
    for s in stages[1:]:
        k = d[f'reached_{s}'].sum(); r, lo, hi = wilson(k, len(d)); pooled.update({f'k_{s}': k, f'rate_{s}': r, f'lo_{s}': lo, f'hi_{s}': hi})
    big = out[out.n >= min_n] if by == 'partner_id' else None
    rows = {'POOLED (account-weighted)': pooled}
    if big is not None and len(big):
        pw = {'n': int(big.n.sum())}
        for s in stages[1:]:
            pw[f'rate_{s}'] = big[f'rate_{s}'].mean()
        rows[f'PARTNER-WEIGHTED (mean of {len(big)} partners with n ≥ {min_n})'] = pw
    summ = pd.DataFrame(rows).T.astype(float)
    return out, summ, d


def funnel_panels(conv, stages, window_days, top=10, min_n=ds.MIN_GROUP_N, pooled=None):
    """By-partner funnel: HORIZONTAL bars, one panel per stage, rows = top partners by n (+ pooled line).
    Rate within group (penetration grammar); pale = n < min_n."""
    t = conv.head(top)[::-1]
    y = np.arange(len(t)); muted = (t.n < min_n).values
    fig, axes = plt.subplots(1, len(stages) - 1, figsize=(4.0 * (len(stages) - 1) + 1, 0.42 * len(t) + 2.2), sharey=True, squeeze=False)
    for ax, s, col in zip(axes[0], stages[1:], RAMP[-(len(stages) - 1):]):
        bars = ax.barh(y, t[f'rate_{s}'], color=[O_PALE if m else col for m in muted],
                       xerr=[t[f'rate_{s}'] - t[f'lo_{s}'], t[f'hi_{s}'] - t[f'rate_{s}']], ecolor='#666', capsize=2, error_kw={'lw': 0.8})
        if pooled is not None:
            p = pooled.loc['POOLED (account-weighted)', f'rate_{s}']
            ax.axvline(p, color=GRAY, lw=1.2, ls='--'); ax.text(p, len(t) - 0.35, f'pooled {pct(p)}', fontsize=7.5, color='#666', ha='left', va='bottom')
        ax.set_xlim(0, 1.0); ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{100*v:.0f}%'))
        ax.grid(axis='x', color='#e6e6e6'); ax.grid(axis='y', visible=False)
        for i, (b, r, k, n) in enumerate(zip(bars, t[f'rate_{s}'], t[f'k_{s}'], t.n)):
            lab = f'{pct(r)} ({int(k):,}/{int(n):,})'
            if b.get_width() > 0.62:                                           # long bar: label inside, right-aligned, white
                ax.text(b.get_width() - 0.02, b.get_y() + b.get_height() / 2, lab, va='center', ha='right', fontsize=8,
                        color='#9a9a9a' if muted[i] else ('white' if col in (BLACK, O_DARK, O_MID) else '#1a1a1a'))
            else:
                ax.text(b.get_width() + 0.02, b.get_y() + b.get_height() / 2, lab, va='center', fontsize=8, color='#9a9a9a' if muted[i] else '#1a1a1a')
        ax.set_title(f'{s.replace("_", " ")} within {window_days}d', loc='left', fontsize=9.5, fontweight='bold')
    axes[0, 0].set_yticks(y); axes[0, 0].set_yticklabels([f'{i} (n={int(n):,})' for i, n in zip(t.index, t.n)])
    for tk, m in zip(axes[0, 0].get_yticklabels(), muted):
        if m:
            tk.set_color('#9a9a9a')
    fig.suptitle(f'Account funnel by partner: N split within group (penetration), {window_days}-day window', x=0.01, y=0.995, ha='left', va='top', fontsize=10.8, fontweight='bold')
    fig.text(0.01, 0.955, f'rate of accounts CREATED that reached each stage within {window_days} days; whiskers = 95% Wilson; dashed = pooled; pale = n < {min_n}; only accounts old enough for the window',
             fontsize=8, color='#666', va='top')
    plt.tight_layout(rect=(0, 0, 1, 0.92))
    note = ('How to read: each bar is a rate WITHIN the partner (bars do not sum to 100%). The top row is the biggest partner by accounts; '
            'the dashed pooled line is account-weighted, so it sits close to that row. Compare a partner to the PARTNER-WEIGHTED row in the table '
            'to judge it against its peers rather than against the mix.')
    return fig, note


def cohort_lines(conv_c, stages, window_days):
    """Conversion by cohort month: one line per stage, CI band on the final stage. True date axis."""
    t = conv_c.sort_index()
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for s, col in zip(stages[1:], RAMP[-(len(stages) - 1):]):
        ax.plot(t.index, t[f'rate_{s}'], color=col, lw=2 if col == BLACK else 1.6, marker='o', ms=3, label=s.replace('_', ' '))
        ax.annotate(pct(t[f'rate_{s}'].iloc[-1]), (t.index[-1], t[f'rate_{s}'].iloc[-1]), xytext=(5, 0), textcoords='offset points', fontsize=8, color=col, va='center')
    last = stages[-1]
    ax.fill_between(t.index, t[f'lo_{last}'], t[f'hi_{last}'], color=BLACK, alpha=0.08, lw=0)
    ax.set_ylim(0, 1); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{100*v:.0f}%'))
    ax.legend(fontsize=8, loc='lower center', ncol=len(stages) - 1, bbox_to_anchor=(0.5, -0.32))
    dsviz.titled(ax, f'{window_days}-day stage conversion by creation cohort', f'cohorts {t.index.min():%Y-%m} to {t.index.max():%Y-%m}; last cohorts with < {window_days} days of age are excluded (censoring); band = 95% Wilson on {last.replace("_", " ")}')
    ax.set_xlabel('account creation month (cohort)')
    plt.tight_layout()
    note = ('How to read: a column view of the cohort triangle — every cohort measured at the SAME age, so differences are cohort quality '
            '(onboarding, partner mix, KYC policy), not maturity. A step down that persists across stages is a mix shift until a partner split says otherwise.')
    return fig, note


# ------------------------------------------------------------------ 2 time to stage
def time_to_stage(st, stages, as_of, max_days=60):
    """Days between consecutive stages among accounts that reached the earlier stage. Step CDF per pair; the
    share that never arrived (as of as_of) is in each panel's subtitle. Percentiles are among arrivers."""
    pairs = list(zip(stages[:-1], stages[1:]))
    rows = []
    fig, axes = plt.subplots(1, len(pairs), figsize=(4.2 * len(pairs) + 0.5, 4.3), squeeze=False)
    for ax, (a, b) in zip(axes[0], pairs):
        base = st[st[a].notna()]
        d = (base[b] - base[a]).dt.total_seconds() / 86400.0
        arrived = d.dropna(); arrived = arrived[arrived >= 0]
        never = 1 - len(arrived) / max(len(base), 1)
        q = arrived.quantile([.25, .5, .75, .9]) if len(arrived) else pd.Series([np.nan] * 4, index=[.25, .5, .75, .9])
        rows.append({'from': a, 'to': b, 'n_reached_from': len(base), 'n_arrived': len(arrived), 'never_arrived_share': round(never, 4),
                     'p25_days': round(q[.25], 2), 'p50_days': round(q[.5], 2), 'p75_days': round(q[.75], 2), 'p90_days': round(q[.9], 2),
                     'within_1d': round((arrived <= 1).mean(), 4) if len(arrived) else np.nan, 'within_7d': round((arrived <= 7).mean(), 4) if len(arrived) else np.nan})
        if len(arrived):
            xs = np.sort(arrived.values); ys = np.arange(1, len(xs) + 1) / len(base)          # CDF of ALL who reached `a`, so it plateaus at 1 - never
            xs = np.r_[0, xs]; ys = np.r_[0, ys]
            ax.step(xs, ys, where='post', color=BLACK, lw=2)
            for m, c in zip([.5, .75, .9], [O_LIGHT, O_MID, O_DARK]):
                ax.axvline(q[m], color=c, lw=1, ls=':'); ax.annotate(f'p{int(m*100)} {q[m]:.1f}d', (q[m], 0.05 + 0.1 * [.5, .75, .9].index(m)), xytext=(4, 0), textcoords='offset points', fontsize=8, color=c)
            ax.axhline(1 - never, color=GRAY, lw=1, ls='--'); ax.text(max_days, 1 - never, f'{pct(1-never)} ever', fontsize=7.5, color='#666', ha='right', va='bottom')
        ax.set_xlim(0, max_days); ax.set_ylim(0, 1.02); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{100*v:.0f}%'))
        ax.set_xlabel(f'days from {a.replace("_", " ")}'); ax.set_ylabel(f'cumulative % of accounts that reached {a.replace("_", " ")}')
        dsviz.titled(ax, f'{a.replace("_", " ")} → {b.replace("_", " ")}', f'n = {len(base):,}; never arrived {pct(never)}; percentiles among arrivers')
    plt.tight_layout()
    table = pd.DataFrame(rows).set_index(['from', 'to'])
    note = ('How to read: each curve plateaus at the share that ever arrived, so the gap to 100% is the drop-off, not slowness. '
            'p50 among arrivers is the honest "typical" number; a mean would be wrecked by accounts that fund and sit in cash.')
    return fig, table, note


# ------------------------------------------------------------------ 3 retention
def retention(ev, st, as_of, anchor='funded', activity_event='trade', max_age=12, min_cohort=50):
    """Cohort = calendar month of `anchor`; active in age k = ≥1 `activity_event` in calendar month anchor_month + k.
    Returns triangle (rows cohorts, cols ages, values rate), sizes, long table, and the quarterly curves figure.
    Ages not yet complete as of as_of are left NaN (right-censoring)."""
    base = st[st[anchor].notna()][['account_id', 'partner_id', anchor]].copy()
    base['cohort'] = base[anchor].dt.to_period('M')
    act = ev[ev.event == activity_event][['account_id', 'ts']].merge(base[['account_id', 'cohort']], on='account_id')
    act['age'] = (act.ts.dt.to_period('M') - act.cohort).apply(lambda x: x.n)
    act = act[(act.age >= 0) & (act.age <= max_age)].drop_duplicates(['account_id', 'age'])
    sizes = base.groupby('cohort').size()
    hits = act.groupby(['cohort', 'age']).size().unstack('age').reindex(index=sizes.index, columns=range(max_age + 1)).fillna(0)
    tri = hits.div(sizes, axis=0)
    last_complete = pd.Timestamp(as_of).to_period('M') - 1                       # the as_of month is partial
    for c in tri.index:
        for k in tri.columns:
            if c + k > last_complete:
                tri.loc[c, k] = np.nan
    tri = tri[sizes >= min_cohort]; sizes = sizes[tri.index]
    # pooled curve (account-weighted over cohorts that have reached each age)
    pooled = pd.Series({k: (tri[k] * sizes).sum() / sizes[tri[k].notna()].sum() if tri[k].notna().any() else np.nan for k in tri.columns})
    # quarterly curves for the chart
    qs = base.assign(q=base[anchor].dt.to_period('Q')).groupby('q').size()
    qidx = tri.index.asfreq('Q')
    w = tri.notna().mul(sizes.values, axis=0).groupby(qidx).sum()          # accounts observed at each age, per quarter
    num = tri.fillna(0).mul(sizes.values, axis=0).groupby(qidx).sum()
    tri_q = (num / w).where(w > 0)
    fig, ax = plt.subplots(figsize=(9, 4.4))
    cols = [O_PALE, O_LIGHT, O_MID, O_DARK, '#7a2a0a', '#4a1a05', '#2a0f03']
    for (q, row), c in zip(tri_q.iterrows(), cols * 3):
        r = row.dropna()
        if len(r) < 2:
            continue
        ax.plot(r.index, r.values, color=c, lw=1.5, marker='o', ms=3, label=f'{q} (n={int(qs.get(q, 0)):,})')
    pr = pooled.dropna(); ax.plot(pr.index, pr.values, color=BLACK, lw=2.4, label='pooled')
    for k in [1, 3, 6]:
        if k in pr.index:
            ax.annotate(f'M{k} {pct(pr[k])}', (k, pr[k]), xytext=(4, 6), textcoords='offset points', fontsize=8, color=BLACK)
    ax.set_ylim(0, 1); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{100*v:.0f}%'))
    ax.set_xticks(range(0, max_age + 1)); ax.set_xticklabels([f'M{k}' for k in range(0, max_age + 1)])
    ax.set_xlabel(f'months since {anchor} (M0 = the {anchor} month, partial)'); ax.set_ylabel(f'% of cohort with ≥1 {activity_event}')
    ax.legend(fontsize=7.5, ncol=2, loc='upper right', title=f'{anchor} cohort (quarter)', title_fontsize=7.5)
    dsviz.titled(ax, f'Retention curves: monthly active after {anchor}', f'active = ≥1 {activity_event} in calendar month k after the {anchor} month; cohorts < {min_cohort} accounts dropped; incomplete ages censored; black = pooled')
    plt.tight_layout()
    tri_out = tri.copy(); tri_out.insert(0, 'size', sizes); tri_out.index = tri_out.index.astype(str)
    note = ('How to read: rows of the printed triangle are one cohort over its life (should only fall or flatten); columns compare cohorts at the same age '
            '(cohort quality); a bump that lines up on one calendar month across cohorts is a calendar event, not a product effect. '
            'Read the diagonal before trusting a column comparison.')
    return fig, tri_out.round(3), pooled.round(4), note


def retention_by_partner(ev, st, as_of, age=3, anchor='funded', activity_event='trade', top_k=10):
    """Penetration view (eda_views) of 'active at age k' among anchor-cohort accounts old enough to have that age."""
    last_complete = pd.Timestamp(as_of).to_period('M') - 1
    base = st[st[anchor].notna()][['account_id', 'partner_id', anchor]].copy()
    base['cohort'] = base[anchor].dt.to_period('M')
    base = base[(base.cohort + age) <= last_complete]
    act = ev[ev.event == activity_event][['account_id', 'ts']].merge(base[['account_id', 'cohort']], on='account_id')
    act = act[(act.ts.dt.to_period('M') - act.cohort).apply(lambda x: x.n) == age]
    base[f'active_m{age}'] = base.account_id.isin(act.account_id).astype(int)
    v = eda_views.penetration(base, 'partner_id', f'active_m{age}', top_k=top_k, flag_label=f'active at M{age}')
    return v.fig, v.table, v.note, base
