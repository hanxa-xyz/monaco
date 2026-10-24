"""causal — quasi-experimental estimators in the house grammar, with the assumption each one buys you printed next to it.

Every method here answers one question in a different costume: what would have happened without the change?
The ladder, strongest claim first:
    randomize it            -> A/B test (not in this module; see cuped() for variance reduction)
    assigned by a cutoff    -> RDD (not implemented; design-specific)
    one unit, many controls -> synthetic control (not implemented; needs a donor pool)
    treated + control over time -> did() / event_study()              assumption: parallel trends
    confounders all measured    -> ipw() with overlap + balance          assumption: conditional ignorability, positivity
    just before vs after        -> its()                                 assumption: the pre-trend would have continued
`method_ladder()` walks that list from a few yes/no answers and returns the method, what to defend, and what breaks it.

Conventions: unit-level cluster bootstrap for standard errors (units are the clusters: partners, geos, shops), never
row-level; coefficients are differences in means, so a reader can rebuild them from the printed cell table;
exploratory language throughout — none of this is a substitute for a holdout when one is possible.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from monaco import viz
from monaco.stats import Z95

SEED = 0


# ------------------------------------------------------------------ helpers
def _period_index(s):
    """Map periods (ints, dates, strings) to 0..k-1 in sorted order; returns (index Series, sorted periods)."""
    periods = np.sort(pd.unique(s.dropna()))
    lookup = {p: i for i, p in enumerate(periods)}
    return s.map(lookup), periods


def _cluster_boot(df, unit, fn, n_boot, seed=SEED, strata=None):
    """Resample units with replacement (within `strata` when given, so every draw keeps both arms), apply
    fn(sample_df) -> scalar or array; returns stacked draws. Draws where fn fails (a degenerate resample) are dropped
    and counted in draws.attrs-like `_cluster_boot.last_dropped`."""
    rng = np.random.default_rng(seed)
    groups = {u: g for u, g in df.groupby(unit)}
    if strata is None:
        pools = [np.array(list(groups))]
    else:
        arm = df.groupby(unit)[strata].max()
        pools = [arm.index[arm == a].to_numpy() for a in sorted(arm.unique())]
    draws, dropped = [], 0
    for _ in range(n_boot):
        pick = np.concatenate([rng.choice(pool, size=len(pool), replace=True) for pool in pools])
        samp = pd.concat([groups[u].assign(**{unit: f'{u}#{i}'}) for i, u in enumerate(pick)], ignore_index=True)
        try:
            v = fn(samp)
        except (TypeError, KeyError, ValueError):
            dropped += 1; continue
        if np.any(~np.isfinite(np.atleast_1d(v))):
            dropped += 1; continue
        draws.append(v)
    _cluster_boot.last_dropped = dropped
    return np.array(draws, dtype=float)


_cluster_boot.last_dropped = 0


# ------------------------------------------------------------------ difference-in-differences
def _did_cells(df, y, treated, post):
    g = df.groupby([treated, post])[y].mean()
    T1, T0 = g.get((1, 1), np.nan), g.get((1, 0), np.nan)
    C1, C0 = g.get((0, 1), np.nan), g.get((0, 0), np.nan)
    return T0, T1, C0, C1


def did(df, unit, period, y, treated, post, n_boot=500, seed=SEED):
    """2x2 difference-in-differences on unit-period rows. ATT = (T_post - T_pre) - (C_post - C_pre), SE by cluster
    bootstrap over units. Returns dict(att, se, lo, hi, p, cells (DataFrame), counterfactual, n_units, n_periods)."""
    d = df[[unit, period, y, treated, post]].dropna().copy()
    d[treated] = d[treated].astype(int); d[post] = d[post].astype(int)
    T0, T1, C0, C1 = _did_cells(d, y, treated, post)
    att = (T1 - T0) - (C1 - C0)
    draws = _cluster_boot(d, unit, lambda s: (lambda a, b, c, e: (b - a) - (e - c))(*_did_cells(s, y, treated, post)), n_boot, seed, strata=treated)
    se = float(np.nanstd(draws, ddof=1))
    lo, hi = att - Z95 * se, att + Z95 * se
    p = float(2 * stats.norm.sf(abs(att / se))) if se > 0 else float('nan')
    cells = pd.DataFrame({'pre': [T0, C0], 'post': [T1, C1]}, index=['treated', 'control'])
    cells['change'] = cells.post - cells.pre
    n_units = d.groupby(treated)[unit].nunique().to_dict()
    caveat = None
    if min(n_units.get(1, 0), n_units.get(0, 0)) < 2:
        caveat = ('one arm has a single unit: the bootstrap only resamples the other arm, so the SE reflects control noise, '
                  'not treated-unit idiosyncrasy. Treat the CI as a floor and lean on the event study.')
    return dict(att=float(att), se=se, lo=float(lo), hi=float(hi), p=p, cells=cells, counterfactual=float(T0 + (C1 - C0)),
                n_treated_units=int(n_units.get(1, 0)), n_control_units=int(n_units.get(0, 0)),
                n_periods=int(d[period].nunique()), n_boot=len(draws), caveat=caveat)


def event_study(df, unit, period, y, treated, treat_period, window=(-6, 6), ref=-1, n_boot=300, seed=SEED):
    """Dynamic DiD: for each relative period r, coef_r = (T_r - C_r) - (T_ref - C_ref). Pre-period coefficients are
    the parallel-trends evidence (they should sit on zero). Returns (table, pretrend) where pretrend = dict(chi2, df, p,
    max_abs_pre). Periods may be ints or dates; `treat_period` is the first treated period."""
    d = df[[unit, period, y, treated]].dropna().copy()
    d[treated] = d[treated].astype(int)
    idx, periods = _period_index(d[period])
    t0 = int(np.searchsorted(periods, treat_period))
    d['rel'] = idx - t0
    d = d[(d.rel >= window[0]) & (d.rel <= window[1])]
    rels = sorted(d.rel.unique())
    if ref not in rels:
        raise SystemExit(f'reference period {ref} not in data (relative periods present: {rels})')

    def coefs(s):
        g = s.groupby(['rel', treated])[y].mean().unstack(treated)
        if 1 not in g.columns or 0 not in g.columns:
            raise ValueError('an arm is missing from this sample')
        gap = g[1] - g[0]
        base = gap.get(ref, np.nan)
        return np.array([gap.get(r, np.nan) - base for r in rels])

    est = coefs(d)
    draws = _cluster_boot(d, unit, coefs, n_boot, seed, strata=treated)
    se = np.nanstd(draws, axis=0, ddof=1)
    n = d.groupby(['rel', treated])[unit].nunique().unstack(treated)
    tab = pd.DataFrame({'rel_period': rels, 'coef': est, 'se': se, 'lo': est - Z95 * se, 'hi': est + Z95 * se,
                        'n_treated': n.get(1).reindex(rels).values, 'n_control': n.get(0).reindex(rels).values}).set_index('rel_period')
    tab['period'] = [periods[t0 + r] if 0 <= t0 + r < len(periods) else None for r in rels]
    pre = [r for r in rels if r < 0 and r != ref]
    if pre:
        j = [rels.index(r) for r in pre]
        z = est[j]; cov = np.cov(draws[:, j], rowvar=False) if len(j) > 1 else np.array([[np.var(draws[:, j[0]], ddof=1)]])
        chi2 = float(z @ np.linalg.pinv(np.atleast_2d(cov)) @ z)
        pretrend = dict(chi2=chi2, df=len(pre), p=float(stats.chi2.sf(chi2, len(pre))), max_abs_pre=float(np.nanmax(np.abs(z))))
    else:
        pretrend = dict(chi2=float('nan'), df=0, p=float('nan'), max_abs_pre=float('nan'))
    return tab, pretrend


def plot_did(df, period, y, treated, treat_period, res=None, y_label=None, fmt=lambda v: f'{v:.2f}'):
    """Treated vs control means over time, counterfactual (treated pre level + control's change) dashed, ATT bracket."""
    d = df.copy(); d[treated] = d[treated].astype(int)
    m = d.groupby([period, treated])[y].mean().unstack(treated).sort_index()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(m.index, m[1], color=viz.BLACK, lw=2.2, marker='o', ms=4, label='treated (observed)')
    ax.plot(m.index, m[0], color=viz.O_MID, lw=2, marker='o', ms=4, label='control')
    pre = m.index < treat_period
    if pre.any() and (~pre).any():
        T0, C0 = m.loc[pre, 1].mean(), m.loc[pre, 0].mean()
        cf = T0 + (m[0] - C0)
        ax.plot(m.index[~pre], cf[~pre], color=viz.BLACK, lw=1.6, ls='--', label='treated counterfactual (= pre level + control change)')
        xs = m.index[~pre]
        ax.vlines(xs[-1], min(m.loc[xs[-1], 1], cf[xs[-1]]), max(m.loc[xs[-1], 1], cf[xs[-1]]), color=viz.O_DARK, lw=2)
        if res is not None:
            ax.annotate(f'ATT {fmt(res["att"])}  [{fmt(res["lo"])}, {fmt(res["hi"])}]', (xs[-1], (m.loc[xs[-1], 1] + cf[xs[-1]]) / 2),
                        xytext=(-8, 0), textcoords='offset points', ha='right', va='center', fontsize=9.5, color=viz.O_DARK)
    ax.axvline(treat_period, color=viz.GRAY, lw=1, ls=':'); ax.text(treat_period, ax.get_ylim()[1], ' treatment starts', color=viz.GRAY, fontsize=8.5, va='top')
    ax.set_ylabel(y_label or y); ax.legend(frameon=False, fontsize=9, loc='best')
    viz.titled(ax, 'Difference-in-differences', 'ATT = (treated post − pre) − (control post − pre); the dashed line is where the treated group would have gone')
    return fig, 'How to read: the control carries seasonality and drift; the gap between the solid and dashed treated lines after the start is the effect. Parallel pre-trends are the evidence; they are support, not proof.'


def plot_event_study(tab, pretrend=None, y_label='effect vs reference period'):
    fig, ax = plt.subplots(figsize=(10, 4.8))
    r = tab.index.values
    ax.axhline(0, color=viz.GRAY, lw=1)
    ax.axvspan(r.min() - 0.5, -0.5, color=viz.GRAY, alpha=0.08, lw=0)
    ax.errorbar(r, tab.coef, yerr=[tab.coef - tab.lo, tab.hi - tab.coef], fmt='o', color=viz.BLACK, ecolor=viz.BLACK, capsize=3, ms=5)
    post = tab.index >= 0
    ax.errorbar(r[post], tab.coef[post], yerr=[(tab.coef - tab.lo)[post], (tab.hi - tab.coef)[post]], fmt='o', color=viz.O_DARK, ecolor=viz.O_DARK, capsize=3, ms=5)
    ax.axvline(-0.5, color=viz.GRAY, lw=1, ls=':')
    ax.set_xlabel('periods relative to treatment start (reference = −1)'); ax.set_ylabel(y_label)
    ax.text(r.min() - 0.3, ax.get_ylim()[1], ' pre-period: should sit on zero', color=viz.GRAY, fontsize=8.5, va='top')
    sub = 'black = pre, orange = post; whiskers = 95% cluster-bootstrap CI'
    if pretrend and np.isfinite(pretrend.get('p', np.nan)):
        sub += f'; joint pre-trend test p = {pretrend["p"]:.2f} (max |pre| = {pretrend["max_abs_pre"]:.3f})'
    viz.titled(ax, 'Event study', sub)
    return fig, 'How to read: pre coefficients on zero support parallel trends; post coefficients are the dynamic effect. A ramp in the pre period means the groups were already diverging and the DiD is not identified.'


# ------------------------------------------------------------------ CUPED (variance reduction for randomized tests)
def cuped(df, y, y_pre, arm, treatment_label=None):
    """CUPED-adjusted lift for a two-arm randomized test. theta = cov(y, y_pre)/var(y_pre) pooled across arms;
    y_adj = y - theta (y_pre - mean y_pre). Returns a one-row-per-method table (naive vs CUPED): diff, se, lo, hi,
    plus theta, the pre-period correlation and the variance reduction. Not a causal fix: only shrinks noise."""
    d = df[[y, y_pre, arm]].dropna().copy()
    arms = sorted(d[arm].unique())
    if len(arms) != 2:
        raise SystemExit(f'cuped() needs exactly two arms, got {arms}')
    t_lab = treatment_label if treatment_label is not None else arms[-1]
    theta = np.cov(d[y], d[y_pre])[0, 1] / np.var(d[y_pre], ddof=1)
    d['y_adj'] = d[y] - theta * (d[y_pre] - d[y_pre].mean())
    rows = []
    for name, col in [('naive', y), ('cuped', 'y_adj')]:
        a = d.loc[d[arm] == t_lab, col]; b = d.loc[d[arm] != t_lab, col]
        diff = a.mean() - b.mean(); se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        rows.append((name, diff, se, diff - Z95 * se, diff + Z95 * se, 2 * stats.norm.sf(abs(diff / se)) if se > 0 else np.nan))
    tab = pd.DataFrame(rows, columns=['method', 'diff', 'se', 'lo', 'hi', 'p']).set_index('method')
    var_red = 1 - (tab.loc['cuped', 'se'] / tab.loc['naive', 'se']) ** 2
    return tab, dict(theta=float(theta), corr=float(np.corrcoef(d[y], d[y_pre])[0, 1]), variance_reduction=float(var_red), n=len(d))


# ------------------------------------------------------------------ propensity / IPW (selection on observables)
def propensity(X, t, max_iter=50, tol=1e-8, ridge=1e-6):
    """Logistic regression by IRLS on standardized X; returns (e, coef) with e clipped to (1e-6, 1-1e-6)."""
    X = np.asarray(X, dtype=float); t = np.asarray(t, dtype=float)
    mu, sd = X.mean(0), X.std(0); sd[sd == 0] = 1
    Z = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    b = np.zeros(Z.shape[1])
    for _ in range(max_iter):
        p = 1 / (1 + np.exp(-Z @ b)); W = p * (1 - p)
        H = Z.T @ (Z * W[:, None]) + ridge * np.eye(Z.shape[1])
        step = np.linalg.solve(H, Z.T @ (t - p))
        b += step
        if np.max(np.abs(step)) < tol:
            break
    e = 1 / (1 + np.exp(-Z @ b))
    return np.clip(e, 1e-6, 1 - 1e-6), b


def smd(x, t, w=None):
    """Standardized mean difference treated − control, pooled SD from the unweighted arms (so before/after are comparable)."""
    x = np.asarray(x, dtype=float); t = np.asarray(t, dtype=int); w = np.ones(len(x)) if w is None else np.asarray(w, dtype=float)
    m1 = np.average(x[t == 1], weights=w[t == 1]); m0 = np.average(x[t == 0], weights=w[t == 0])
    s = np.sqrt((x[t == 1].var(ddof=1) + x[t == 0].var(ddof=1)) / 2)
    return (m1 - m0) / s if s > 0 else 0.0


def ipw(df, treated, y, covariates, estimand='ATT', trim=(0.01, 0.99), n_boot=300, seed=SEED, unit=None):
    """Inverse-probability-weighted effect with overlap trimming, stabilized weights, effective sample size, and the
    balance table (SMD before vs after). ATT weights: treated 1, control e/(1-e). ATE weights: 1/e and 1/(1-e).
    SE by bootstrap (over `unit` clusters when given, else rows). Returns dict + balance DataFrame + overlap frame."""
    d = df[[treated, y] + list(covariates) + ([unit] if unit else [])].dropna().copy()
    d[treated] = d[treated].astype(int)
    e, _ = propensity(d[covariates].values, d[treated].values)
    d['e'] = e
    keep = (d.e >= trim[0]) & (d.e <= trim[1])
    n_trim = int((~keep).sum())
    dk = d[keep].copy()

    def weights(s):
        if estimand.upper() == 'ATT':
            w = np.where(s[treated] == 1, 1.0, s.e / (1 - s.e))
        else:
            w = np.where(s[treated] == 1, 1 / s.e, 1 / (1 - s.e))
        # stabilize: each arm's weights sum to its n
        for a in (0, 1):
            m = s[treated].values == a
            w[m] *= m.sum() / w[m].sum()
        return w

    def effect(s):
        w = weights(s)
        m1 = np.average(s.loc[s[treated] == 1, y], weights=w[s[treated].values == 1])
        m0 = np.average(s.loc[s[treated] == 0, y], weights=w[s[treated].values == 0])
        return m1 - m0

    est = effect(dk)
    if unit:
        draws = _cluster_boot(dk, unit, effect, n_boot, seed)
    else:
        rng = np.random.default_rng(seed)
        draws = np.array([effect(dk.sample(len(dk), replace=True, random_state=int(rng.integers(1e9)))) for _ in range(n_boot)])
    se = float(np.nanstd(draws, ddof=1))
    w = weights(dk); dk['w'] = w
    ess = {a: float(w[dk[treated].values == a].sum() ** 2 / (w[dk[treated].values == a] ** 2).sum()) for a in (0, 1)}
    bal = pd.DataFrame({'smd_before': [smd(d[c], d[treated]) for c in covariates],
                        'smd_after': [smd(dk[c], dk[treated], dk.w) for c in covariates]}, index=list(covariates))
    bal['balanced_after'] = bal.smd_after.abs() < 0.10
    naive = d.loc[d[treated] == 1, y].mean() - d.loc[d[treated] == 0, y].mean()
    res = dict(estimand=estimand.upper(), effect=float(est), se=se, lo=float(est - Z95 * se), hi=float(est + Z95 * se),
               p=float(2 * stats.norm.sf(abs(est / se))) if se > 0 else float('nan'), naive_diff=float(naive),
               n_treated=int((dk[treated] == 1).sum()), n_control=int((dk[treated] == 0).sum()), n_trimmed=n_trim,
               ess_treated=ess[1], ess_control=ess[0], max_weight=float(w.max()), trim=trim)
    return res, bal, d[[treated, 'e']]


def plot_overlap(overlap, treated, trim=(0.01, 0.99)):
    fig, ax = plt.subplots(figsize=(9, 4.4))
    bins = np.linspace(0, 1, 41)
    ax.hist(overlap.loc[overlap[treated] == 0, 'e'], bins=bins, color=viz.O_MID, alpha=0.75, label='control', density=True)
    ax.hist(overlap.loc[overlap[treated] == 1, 'e'], bins=bins, color=viz.BLACK, alpha=0.55, label='treated', density=True)
    ax.axvspan(0, trim[0], color=viz.GRAY, alpha=0.15, lw=0); ax.axvspan(trim[1], 1, color=viz.GRAY, alpha=0.15, lw=0)
    ax.set_xlabel('propensity e(X) = P(treated | X)'); ax.set_ylabel('density'); ax.legend(frameon=False, fontsize=9)
    viz.titled(ax, 'Overlap (positivity check)', f'grey = trimmed outside [{trim[0]}, {trim[1]}]; regions where only one arm has mass have no comparison')
    return fig, 'How to read: the weighted estimate is only as good as the region where both histograms have mass. Separation = extrapolation, not estimation.'


def plot_balance(bal):
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(bal) + 2))
    yv = np.arange(len(bal))
    ax.scatter(bal.smd_before.abs(), yv, color=viz.GRAY, s=36, label='before weighting', zorder=3)
    ax.scatter(bal.smd_after.abs(), yv, color=viz.BLACK, s=36, label='after weighting', zorder=4)
    for i, (b, a) in enumerate(zip(bal.smd_before.abs(), bal.smd_after.abs())):
        ax.plot([b, a], [i, i], color=viz.O_LIGHT, lw=1.5, zorder=2)
    ax.axvline(0.10, color=viz.O_DARK, lw=1, ls=':'); ax.text(0.10, len(bal) - 0.4, ' |SMD| = 0.10', color=viz.O_DARK, fontsize=8.5)
    ax.set_yticks(yv); ax.set_yticklabels(bal.index); ax.set_xlabel('|standardized mean difference|'); ax.set_xlim(left=0)
    ax.legend(frameon=False, fontsize=9, loc='lower right')
    viz.titled(ax, 'Covariate balance', 'treated vs control, before and after IPW; everything should land left of the dotted line')
    return fig, 'How to read: balance after weighting is necessary, not sufficient; unmeasured confounders are untouched by construction.'


# ------------------------------------------------------------------ interrupted time series (last resort)
def its(df, period, y, treat_period):
    """Segmented regression y = a + b·t + c·post + d·post·(t − t0). Reports level change c and slope change d with OLS
    SEs. No control group, so anything else that changed at t0 is in the estimate. Say so in the readout."""
    d = df[[period, y]].dropna().sort_values(period).copy()
    idx, periods = _period_index(d[period]); t0 = int(np.searchsorted(periods, treat_period))
    t = idx.values.astype(float); post = (t >= t0).astype(float)
    X = np.column_stack([np.ones(len(t)), t, post, post * (t - t0)])
    beta, res, rank, _ = np.linalg.lstsq(X, d[y].values, rcond=None)
    resid = d[y].values - X @ beta; dof = max(len(t) - X.shape[1], 1)
    cov = np.linalg.pinv(X.T @ X) * (resid @ resid / dof)
    se = np.sqrt(np.diag(cov))
    tab = pd.DataFrame({'coef': beta, 'se': se, 'lo': beta - Z95 * se, 'hi': beta + Z95 * se},
                       index=['intercept', 'pre_slope', 'level_change', 'slope_change'])
    return tab, dict(n_pre=int((post == 0).sum()), n_post=int(post.sum()))


# ------------------------------------------------------------------ the ladder
LADDER = [
    ('randomize', 'A/B test (randomized holdout)', 'strongest', 'proper randomization; no interference (SUTVA)', 'underpowered tests, peeking, novelty effects'),
    ('cutoff', 'Regression discontinuity', 'design-based', 'continuity at the cutoff; no manipulation of the running variable', 'effect is local to the threshold; bunching'),
    ('nudge', 'Instrumental variable / encouragement design', 'design-based', 'relevance; exclusion restriction; monotonicity (estimates a LATE)', 'weak or invalid instruments; compliers only'),
    ('one_unit_many_controls', 'Synthetic control', 'design-based', 'good pre-period fit; clean donors; no spillover', 'overfitting the pre-period; no valid donors'),
    ('panel_pre_post', 'Difference-in-differences / event study', 'design-based', 'parallel trends; no anticipation; stable composition', 'differential trends; staggered-rollout TWFE bias'),
    ('confounders_measured', 'IPW / propensity (prefer doubly robust)', 'adjustment', 'no unmeasured confounding; positivity / overlap', 'hidden confounders; extreme weights'),
    ('pre_post_only', 'Interrupted time series', 'weakest', 'the pre-trend would have continued; no co-occurring shocks', 'anything else that changed at the same time'),
]


def method_ladder(**answers):
    """Walk the ladder with yes/no answers (randomize, cutoff, nudge, one_unit_many_controls, panel_pre_post,
    confounders_measured, pre_post_only). Returns the first rung answered True, plus the full ladder as a table."""
    tab = pd.DataFrame(LADDER, columns=['question', 'method', 'strength', 'assumption_to_defend', 'main_pitfall']).set_index('question')
    for q, method, strength, assumption, pitfall in LADDER:
        if answers.get(q):
            return dict(method=method, strength=strength, assumption=assumption, pitfall=pitfall, question=q), tab
    return dict(method=None, strength=None, assumption=None, pitfall=None, question=None), tab
