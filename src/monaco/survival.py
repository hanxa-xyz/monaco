"""survival — time-to-event with censoring, in the house grammar. Kaplan-Meier without lifelines.

Contract (one row per entity):
    duration   time from t0 to the event or to censoring (any unit; say it in the label)
    event      1 = the event happened at `duration`, 0 = censored (still at risk when observation stopped)
    group      optional split (partner, cohort, arm)

`from_timestamps()` builds that from (start, end, as_of) columns. Views return (fig | None, table, note) and every
table is meant to be printed next to its chart.

What KM adds over a naive cohort read: censored entities stay in the risk set until they leave, instead of being
dropped (which biases the curve down) or counted as survivors (which biases it up). The price is the
non-informative-censoring assumption: being censored must not predict the event. Say that out loud once per readout.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from monaco import viz
from monaco.stats import Z95, pct

THIN_RISK = 10            # below this many at risk the tail is hazy: shade it, do not read it
MIN_GROUP = 30            # groups smaller than this are reported in tables but not drawn
GROUP_RAMP = [viz.O_DARK, viz.O_MID, viz.O_LIGHT, viz.O_PALE, '#7a2d0c', '#f7b98f']


# ------------------------------------------------------------------ shaping
def from_timestamps(df, start, end, as_of=None, group=None, unit='D', entity=None):
    """(start, end-or-null, as_of) -> duration/event[/group]. `end` null = censored at as_of. Rows with start > as_of
    or missing start are dropped and counted in the note."""
    d = df.copy()
    d[start] = pd.to_datetime(d[start]); d[end] = pd.to_datetime(d[end])
    as_of = pd.Timestamp(as_of) if as_of is not None else max(d[start].max(), d[end].max())
    n0 = len(d)
    d = d[d[start].notna() & (d[start] <= as_of)]
    stop = d[end].where(d[end].notna() & (d[end] <= as_of), as_of)
    out = pd.DataFrame({
        'duration': (stop - d[start]) / pd.Timedelta(1, unit=unit),
        'event': (d[end].notna() & (d[end] <= as_of)).astype(int),
    }, index=d.index)
    if group is not None:
        out['group'] = d[group].astype(str).values
    if entity is not None:
        out.insert(0, 'entity_id', d[entity].values)
    out = out[out.duration >= 0]
    out.attrs['note'] = (f'{len(out):,} of {n0:,} rows kept (start present and ≤ as_of {as_of:%Y-%m-%d}); '
                         f'{int(out.event.sum()):,} events, {int((1 - out.event).sum()):,} censored; unit = {unit}')
    out.attrs['as_of'] = as_of
    return out


# ------------------------------------------------------------------ estimators
def km(duration, event):
    """Kaplan-Meier table: one row per distinct event time with t, n_risk, d, c (censored at t), S, se, lo, hi (Greenwood,
    on the log(-log S) scale so the band stays inside [0, 1]). Row 0 is t=0, S=1."""
    t = np.asarray(duration, dtype=float); e = np.asarray(event, dtype=int)
    order = np.argsort(t, kind='mergesort'); t, e = t[order], e[order]
    times = np.unique(t[e == 1])
    n = len(t); rows = [(0.0, n, 0, 0, 1.0, 0.0, 1.0, 1.0)]
    S, var_term = 1.0, 0.0
    for ti in times:
        at_risk = int((t >= ti).sum())
        d = int(((t == ti) & (e == 1)).sum())
        c = int(((t == ti) & (e == 0)).sum())
        if at_risk == 0:
            break
        S *= 1 - d / at_risk
        if at_risk - d > 0:
            var_term += d / (at_risk * (at_risk - d))
        se = S * np.sqrt(var_term)
        if 0 < S < 1:
            # log-log transform: bounds = S ** exp(±z * se / (S log S))
            w = Z95 * np.sqrt(var_term) / abs(np.log(S))
            lo, hi = S ** np.exp(w), S ** np.exp(-w)
        else:
            lo, hi = S, S
        rows.append((ti, at_risk, d, c, S, se, lo, hi))
    tab = pd.DataFrame(rows, columns=['t', 'n_risk', 'd', 'c', 'S', 'se', 'lo', 'hi'])
    tab.attrs['n'] = n; tab.attrs['events'] = int(e.sum()); tab.attrs['t_max'] = float(t.max()) if n else 0.0
    return tab


def survival_at(tab, times):
    """S(t) stepwise (right-continuous) at the requested times, with n at risk just before each."""
    out = []
    for x in times:
        row = tab[tab.t <= x].iloc[-1]
        n_risk = int((tab[tab.t >= x].n_risk.max()) if (tab.t >= x).any() else 0)
        out.append((x, row.S, row.lo, row.hi, n_risk))
    return pd.DataFrame(out, columns=['t', 'S', 'lo', 'hi', 'n_risk_after'])


def median_survival(tab):
    """First t where S <= 0.5; NaN if the curve never crosses (say 'median not reached', never 'infinite')."""
    hit = tab[tab.S <= 0.5]
    return float(hit.t.iloc[0]) if len(hit) else float('nan')


def rmst(tab, tau):
    """Restricted mean survival time: area under S(t) up to tau. The honest 'average lifetime' when the median is not reached."""
    t = np.append(tab.t.values, tau); S = np.append(tab.S.values, tab.S.values[-1])
    keep = t <= tau
    t, S = t[keep], S[keep]
    if t[-1] < tau:
        t = np.append(t, tau); S = np.append(S, S[-1])
    return float(np.sum(np.diff(t) * S[:-1]))


def at_risk_table(tab, times):
    return pd.Series([int(tab[tab.t >= x].n_risk.max()) if (tab.t >= x).any() else 0 for x in times], index=times, name='n_at_risk')


def hazard_window(tab, width):
    """Interval of length `width` with the largest drop in S (the peak-hazard window). Returns (t0, t1, drop)."""
    grid = np.arange(0, tab.attrs.get('t_max', tab.t.max()) + width, width)
    s = survival_at(tab, grid).S.values
    drops = s[:-1] - s[1:]
    if len(drops) == 0:
        return (0.0, width, 0.0)
    i = int(np.argmax(drops))
    return (float(grid[i]), float(grid[i + 1]), float(drops[i]))


def logrank(df, group='group', duration='duration', event='event'):
    """Log-rank test across k groups: chi2, df, p. Null = identical survival curves."""
    d = df[[group, duration, event]].dropna()
    groups = sorted(d[group].unique()); k = len(groups)
    times = np.unique(d.loc[d[event] == 1, duration])
    O = np.zeros(k); E = np.zeros(k); V = np.zeros((k, k))
    for ti in times:
        at = d[d[duration] >= ti]; ev = d[(d[duration] == ti) & (d[event] == 1)]
        n = len(at); dd = len(ev)
        if n == 0:
            continue
        n_g = np.array([(at[group] == g).sum() for g in groups], dtype=float)
        d_g = np.array([(ev[group] == g).sum() for g in groups], dtype=float)
        e_g = dd * n_g / n
        O += d_g; E += e_g
        if n > 1:
            V += (dd * (n - dd) / (n - 1)) * (np.diag(n_g / n) - np.outer(n_g / n, n_g / n))
    z = (O - E)[:-1]; Vk = V[:-1, :-1]
    chi2 = float(z @ np.linalg.pinv(Vk) @ z) if k > 1 else 0.0
    p = float(stats.chi2.sf(chi2, k - 1)) if k > 1 else 1.0
    tab = pd.DataFrame({'observed': O, 'expected': E.round(1), 'O/E': (O / np.where(E > 0, E, np.nan)).round(2)}, index=groups)
    return chi2, k - 1, p, tab


def naive_vs_km(df, times, duration='duration', event='event'):
    """At each mark: KM S(t) vs the naive cohort read that drops censored entities ('closed cohort only') and the
    other naive read that treats censored as survivors. The gaps are the censoring bias, both directions."""
    tab = km(df[duration], df[event])
    s = survival_at(tab, times)
    rows = []
    for x, S in zip(s.t, s.S):
        observed = df[(df[event] == 1) | (df[duration] >= x)]            # entities whose status at x is known
        naive_drop = 1 - ((observed[event] == 1) & (observed[duration] <= x)).mean() if len(observed) else np.nan
        naive_keep = 1 - ((df[event] == 1) & (df[duration] <= x)).mean()
        rows.append((x, S, naive_drop, naive_keep, len(observed), len(df)))
    return pd.DataFrame(rows, columns=['t', 'km_S', 'naive_known_status_only', 'naive_censored_as_survivors', 'n_known', 'n_all'])


# ------------------------------------------------------------------ views
def _step(ax, tab, color, label, lw=2.0, band=True, z=3):
    t = tab.t.values; S = tab.S.values
    ax.step(t, S, where='post', color=color, lw=lw, label=label, zorder=z)
    if band:
        ax.fill_between(t, tab.lo.values, tab.hi.values, step='post', color=color, alpha=0.13, lw=0, zorder=z - 1)
    tmax = tab.attrs.get('t_max', t.max())
    if tmax > t[-1]:
        ax.hlines(S[-1], t[-1], tmax, color=color, lw=lw, zorder=z)
        ax.fill_between([t[-1], tmax], [tab.lo.values[-1]] * 2, [tab.hi.values[-1]] * 2, color=color, alpha=0.13, lw=0)


def plot_km(curves, marks, unit_label='days', title='Survival', subtitle=None, thin=THIN_RISK, show_at_risk=True, median_line=True, xmax=None):
    """curves: {name: km table} in draw order; the first is the hero (black), the rest use the orange ramp.
    Shades the region where the hero's risk set is below `thin`; prints n at risk under the axis at the marks.
    `xmax` clips the axis (default: the data's max time); pass ~1.15 × the last mark when the event is fast and the tail long."""
    names = list(curves)
    fig, ax = plt.subplots(figsize=(10, 5.6 + (0.28 * len(names) if show_at_risk else 0)))
    colors = [viz.BLACK] + GROUP_RAMP
    for i, name in enumerate(names):
        tab = curves[name]
        _step(ax, tab, colors[i % len(colors)], f'{name} (n={tab.attrs["n"]:,}, events={tab.attrs["events"]:,})')
    hero = curves[names[0]]
    thin_from = hero[hero.n_risk < thin].t.min() if (hero.n_risk < thin).any() else None
    xmax = xmax or max(tab.attrs.get('t_max', tab.t.max()) for tab in curves.values())
    if thin_from is not None and thin_from < xmax:
        ax.axvspan(thin_from, xmax, color=viz.GRAY, alpha=0.10, lw=0)
        ax.text(thin_from, 0.03, f'  < {thin} at risk →', color=viz.GRAY, fontsize=8.5, va='bottom')
    if median_line:
        m = median_survival(hero)
        if np.isfinite(m):
            ax.plot([0, m, m], [0.5, 0.5, 0], ls=':', color=viz.O_DARK, lw=1.2)
            ax.text(m, 0.52, f' median {m:,.1f} {unit_label}', color=viz.O_DARK, fontsize=9, va='bottom')
    for x in marks:
        row = survival_at(hero, [x]).iloc[0]
        ax.plot([x], [row.S], 'o', color=viz.BLACK, ms=4.5, zorder=5)
        ax.annotate(pct(row.S), (x, row.S), xytext=(0, 7), textcoords='offset points', ha='center', fontsize=9, color=viz.BLACK)
    ax.set_ylim(0, 1.02); ax.set_xlim(0, xmax * 1.02)
    ax.set_xlabel(f'time since t0 ({unit_label})'); ax.set_ylabel('S(t) = share still event-free')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.0%}'))
    ax.legend(frameon=False, fontsize=9, loc='upper right')
    viz.titled(ax, title, subtitle or f'Kaplan-Meier; band = 95% CI (Greenwood, log-log); dots = S at {", ".join(str(m) for m in marks)} {unit_label}; grey = thin tail')
    if show_at_risk:
        y0 = -0.16
        ax.text(0, y0 + 0.005, 'at risk', transform=ax.get_xaxis_transform(), fontsize=8.5, color=viz.GRAY, ha='right', va='top')
        for i, name in enumerate(names):
            ar = at_risk_table(curves[name], marks)
            for x, n_ in ar.items():
                ax.text(x, y0 - 0.055 * i, f'{n_:,}', transform=ax.get_xaxis_transform(), fontsize=8.5,
                        color=colors[i % len(colors)], ha='center', va='top')
        fig.subplots_adjust(bottom=0.16 + 0.045 * len(names))
    note = ('How to read: each step down is an event; censored entities leave the risk set without counting as events. '
            'Read S at the marks, the median (first crossing of 50%), and the slope: the steepest stretch is where the hazard peaks. '
            'Do not read the shaded tail.')
    return fig, note


def plot_naive_vs_km(cmp, unit_label='days'):
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(cmp.t, cmp.km_S, color=viz.BLACK, lw=2, marker='o', ms=4, label='Kaplan-Meier (censoring handled)')
    ax.plot(cmp.t, cmp.naive_known_status_only, color=viz.O_MID, lw=1.6, ls='--', marker='s', ms=4, label='naive: known-status entities only (drops censored)')
    ax.plot(cmp.t, cmp.naive_censored_as_survivors, color=viz.O_PALE, lw=1.6, ls='--', marker='^', ms=4, label='naive: censored counted as survivors')
    for x, a, b in zip(cmp.t, cmp.km_S, cmp.naive_known_status_only):
        ax.annotate(f'{100*(b-a):+.0f} pp', (x, b), xytext=(0, -12), textcoords='offset points', ha='center', fontsize=8, color=viz.O_DARK)
    ax.set_ylim(0, 1.02); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.0%}'))
    ax.set_xlabel(f'time since t0 ({unit_label})'); ax.set_ylabel('share still event-free')
    ax.legend(frameon=False, fontsize=9, loc='lower left')
    viz.titled(ax, 'What KM adds beyond a cohort read', 'gap between the lines = censoring bias; labels = naive-known-status minus KM, in points')
    return fig, 'How to read: both naive lines are wrong in opposite directions; the gap grows with the share censored, i.e. with how recent the cohort is.'
