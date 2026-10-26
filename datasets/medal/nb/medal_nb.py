"""Shared helpers for the three Medal case notebooks (datasets/medal/nb/build_0*.py).

Loads datasets/medal/out, derives per-player daily rates, fits the projected pre-launch baseline (log-linear + weekday),
prints rate tables with Wilson intervals, and draws in the house grammar (monaco.viz). Every function returns the table it
charts so the notebook can print it.
"""
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats as st

from monaco.stats import wilson
from monaco.viz import BLACK, GRAY, O_DARK, O_LIGHT, O_MID, O_PALE, apply_style, titled

OUT = Path(__file__).resolve().parents[1] / "out"
LAUNCH = {1: pd.Timestamp("2026-05-07"), 2: pd.Timestamp("2026-05-21"), 3: pd.Timestamp("2025-09-15")}
NAME = {1: "Rocket League", 2: "Ghost Janitors", 3: "Valorant", 4: "Marvel Rivals", 5: "Phasmophobia", 6: "Lethal Company"}
AS_OF = pd.Timestamp("2026-09-01")
PRE, RAMP, POST, FIT = 28, 14, 28, 56          # windows in days: PRE mean, client ramp skipped, POST mean, baseline fit length
MATERIAL = 0.03
D = lambda n: pd.Timedelta(days=n)  # noqa: E731
DATES = {
    "clips": ["captured_ts", "deleted_ts", "shared_ts"], "sessions": ["session_date", "start_ts"], "players": ["signup_date"],
    "game_daily": ["date"], "studio_daily": ["date"], "outcomes_14d_by_trigger": ["week"], "game_weekly_panel": ["week"],
    "player_launch_cohort": ["first_autoclip_date"], "return_rate_player_days": ["session_date"], "studio_monthly": ["month"],
}


def load(*names):
    """Read tables from datasets/medal/out by name; returns a dict."""
    return {n: pd.read_csv(OUT / f"{n}.csv", parse_dates=DATES.get(n)) for n in names}


def setup():
    apply_style(dpi=110)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)


# ------------------------------------------------------------------ daily rates
METRICS = [
    ("players", "Medal players in game", "confounded"), ("clips_total", "Clips captured, all", "data volume"),
    ("clips_manual", "Manual (hotkey) clips", "data volume"), ("manual_pp", "Manual clips / player", "cannibalization"),
    ("shares", "Clips shared off-Medal", "engagement"), ("shares_pp", "Shares / player", "engagement"),
    ("pct_sharing", "% players sharing", "engagement"), ("share_per_clip", "Shares / clip", "dilution"),
    ("posts_pp", "Public posts / player", "engagement"), ("deletes_pp", "Deletions / player (client, any-age)", "curation burden"),
]
LABEL = {m: lbl for m, lbl, _ in METRICS}


def derive_daily(gd, game_id):
    """game_daily rows for one game -> daily frame on a complete date index with manual/auto split and per-player rates."""
    d = gd[gd.game_id == game_id].sort_values("date").drop_duplicates("date").set_index("date").asfreq("D")
    d["clips_manual"] = d.clips_total - d.clips_autoclip_native - d.clips_autoclip_steam_achievement
    d["clips_auto"] = d.clips_autoclip_native + d.clips_autoclip_steam_achievement
    p = d.players.replace(0, np.nan)
    d["manual_pp"], d["auto_pp"] = d.clips_manual / p, d.clips_auto / p
    d["shares"] = d.clips_shared_distinct
    d["shares_pp"], d["pct_sharing"] = d.shares / p, d.users_sharing / p
    d["share_per_clip"] = d.shares / d.clips_total.replace(0, np.nan)
    d["posts_pp"], d["deletes_pp"] = d.public_posts_total / p, d.clips_deleted_distinct / p
    return d


def spikes(s, window=21, ratio=1.6, pad=1):
    """Days far above a centred rolling median (bulk purges, sales). Returns a boolean Series."""
    med = s.rolling(window, center=True, min_periods=window // 2).median()
    m = (s / med.replace(0, np.nan)) > ratio
    for _ in range(pad):
        m = m | m.shift(1, fill_value=False) | m.shift(-1, fill_value=False)
    return m.fillna(False)


# ------------------------------------------------------------------ projected baseline (the packet-only estimator)
def _design(idx, t0, trend):
    t = (idx - t0).days.values.astype(float)
    dow = np.eye(7)[idx.dayofweek.values][:, 1:]
    return np.column_stack([np.ones(len(idx)), t, dow] if trend else [np.ones(len(idx)), dow])


def its_lift(s, launch, trend=False, exclude=None):
    """log(y) ~ level [+ trend] + weekday on the FIT days before launch, projected over POST (after RAMP).
    lift = actual / projected − 1; 95% CI from the projection error + POST noise, inflated for lag-1 autocorrelation."""
    s = s.astype(float)
    ex = exclude.reindex(s.index, fill_value=False) if exclude is not None else pd.Series(False, s.index)
    w = s[(s.index >= launch - D(FIT)) & (s.index < launch)]
    w = w[(w > 0) & w.notna() & ~ex.reindex(w.index, fill_value=False)]
    post = s[(s.index >= launch + D(RAMP)) & (s.index < launch + D(RAMP + POST))]
    post = post[(post > 0) & post.notna() & ~ex.reindex(post.index, fill_value=False)]
    if len(w) < 21 or len(post) < 7:
        return None
    X, y = _design(w.index, launch, trend), np.log(w.values)
    XtX_inv = np.linalg.pinv(X.T @ X); beta = XtX_inv @ X.T @ y
    e = y - X @ beta; s2 = e @ e / max(len(y) - X.shape[1], 1)
    rho = float(np.clip(np.nan_to_num(pd.Series(e).autocorr(1)), 0, 0.9)); infl = (1 + rho) / (1 - rho)
    Xp = _design(post.index, launch, trend); cf_post = np.exp(Xp @ beta + s2 / 2)
    log_lift = np.log(post.sum() / cf_post.sum())
    xbar = Xp.mean(0); se = np.sqrt(s2 * infl * (xbar @ XtX_inv @ xbar + 1 / len(post)))
    full = pd.date_range(launch - D(FIT), launch + D(RAMP + POST) - D(1))
    cf = pd.Series(np.exp(_design(full, launch, trend) @ beta + s2 / 2), full)
    return dict(lift=np.exp(log_lift) - 1, lo=np.exp(log_lift - 1.96 * se) - 1, hi=np.exp(log_lift + 1.96 * se) - 1, cf=cf,
                pre=w.mean(), post=post.mean(), n_fit=len(w), n_post=len(post))


def assess(s, launch, trend=False, exclude=None):
    r = its_lift(s, launch, trend, exclude)
    ex = exclude.reindex(s.index, fill_value=False) if exclude is not None else pd.Series(False, s.index)
    pre = s[(s.index >= launch - D(PRE)) & (s.index < launch) & ~ex].mean()
    post = s[(s.index >= launch + D(RAMP)) & (s.index < launch + D(RAMP + POST)) & ~ex].mean()
    out = dict(pre=pre, post=post, naive=post / pre - 1 if pre else np.nan, lift=np.nan, lo=np.nan, hi=np.nan, call="n/a", cf=None)
    if r:
        sig = r["lo"] > 0 or r["hi"] < 0
        call = "within noise" if not sig else (("UP" if r["lift"] > 0 else "DOWN") if abs(r["lift"]) >= MATERIAL else "small ±")
        out.update(lift=r["lift"], lo=r["lo"], hi=r["hi"], call=call, cf=r["cf"])
    return out


def scorecard(d, launch, metrics=METRICS, exclude_for=("deletes_pp",), exclude=None):
    rows, res = [], {}
    for m, lbl, role in metrics:
        if m not in d or d[m].notna().sum() < 30:
            continue
        r = assess(d[m], launch, exclude=exclude if m in exclude_for else None)
        res[m] = r
        rows.append(dict(metric=lbl, role=role, pre=r["pre"], post=r["post"], naive=r["naive"], vs_baseline=r["lift"],
                         ci95="" if np.isnan(r["lo"]) else f"{r['lo']:+.1%} … {r['hi']:+.1%}", call=r["call"]))
    return pd.DataFrame(rows), res


def fmt_scorecard(sc):
    out = sc.copy()
    pct = {"% players sharing", "Shares / clip"}
    for c in ("pre", "post"):
        out[c] = [f"{v:.1%}" if m in pct else (f"{v:,.2f}" if abs(v) < 20 else f"{v:,.0f}") if pd.notna(v) else ""
                  for m, v in zip(out.metric, out[c])]
    for c in ("naive", "vs_baseline"):
        out[c] = [f"{v:+.1%}" if pd.notna(v) else "" for v in out[c]]
    return out


def plot_metrics(d, launch, res, metrics, title, ncols=3, exclude=None):
    """Small multiples: 7-day rolling actual (black), projected baseline (dotted grey), PRE grey / POST orange bands."""
    metrics = [m for m in metrics if m in res]
    nrows = int(np.ceil(len(metrics) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 2.9 * nrows), squeeze=False)
    for ax, m in zip(axes.flat, metrics):
        r = res[m]; s = d[m].rolling(7, min_periods=4).mean()
        ax.plot(s.index, s, color=BLACK, lw=1.4)
        if r["cf"] is not None:
            cf = r["cf"].rolling(7).mean(); ax.plot(cf.index, cf, color=GRAY, ls=":", lw=1.8)
        ax.axvspan(launch - D(PRE), launch, color="#f0f0f0", lw=0)
        ax.axvspan(launch + D(RAMP), launch + D(RAMP + POST), color=O_PALE, alpha=.5, lw=0)
        ax.axvline(launch, color=GRAY, ls="--", lw=1)
        if exclude is not None and m == "deletes_pp":
            for a, b in spans(exclude):
                ax.axvspan(a, b, color=O_DARK, alpha=.15, lw=0)
        ax.xaxis.set_major_locator(mdates.MonthLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.set_title(LABEL.get(m, m), loc="left", fontsize=9.5, fontweight="bold", pad=14)
        ax.text(0, 1.015, f"vs baseline {r['lift']:+.1%} · {r['call']} · CI {r['lo']:+.1%} … {r['hi']:+.1%}" if not np.isnan(r["lift"]) else "n/a",
                transform=ax.transAxes, fontsize=7.6, color=O_DARK if r["call"] in ("UP", "DOWN") else "#666")
    for ax in list(axes.flat)[len(metrics):]:
        ax.axis("off")
    fig.suptitle(title, x=0.01, ha="left", fontweight="bold")
    fig.text(0.01, 0.945, "black = 7-day rolling actual · dotted grey = baseline fit on 8 pre-launch weeks (level + weekday) · grey band = PRE, orange = POST",
             fontsize=8, color="#666")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return fig


def spans(mask):
    out, start, prev = [], None, None
    for day, v in mask.items():
        if v and start is None:
            start = day
        if not v and start is not None:
            out.append((start, prev)); start = None
        prev = day
    if start is not None:
        out.append((start, prev))
    return out


def plot_composition(d, launch, name):
    fig, ax = plt.subplots(figsize=(10, 3.4))
    for c, lbl, col in (("clips_manual", "manual (hotkey)", BLACK), ("clips_autoclip_native", "native auto-clip", O_MID),
                        ("clips_autoclip_steam_achievement", "Steam-achievement auto-clip", O_LIGHT)):
        s = d[c].rolling(7, min_periods=4).mean(); ax.plot(s.index, s, color=col, lw=1.8, label=lbl)
        last = s.dropna(); ax.annotate(f"{last.iloc[-1]:,.0f}", (last.index[-1], last.iloc[-1]), xytext=(4, 0), textcoords="offset points", fontsize=8, color=col, va="center")
    ax.axvline(launch, color=GRAY, ls="--", lw=1); ax.axvspan(launch, launch + D(RAMP), color=O_PALE, alpha=.35, lw=0)
    ax.xaxis.set_major_locator(mdates.MonthLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.legend(loc="upper left", fontsize=8)
    titled(ax, f"{name}: where the clips come from", "clips per day by trigger source, 7-day rolling · dashed = launch, shaded = 2-week client ramp")
    return fig


# ------------------------------------------------------------------ rates with intervals
def rate_table(df, by, flags, min_n=30):
    """Per group in `by`: n and, for each 0/1 flag column, k, rate, Wilson lo/hi. Groups with n < min_n are kept but marked thin."""
    g = df.groupby(by, dropna=False)
    out = pd.DataFrame({"n": g.size()})
    for f in flags:
        k = g[f].sum(); p, lo, hi = wilson(k.values, out.n.values)
        out[f"{f}_k"], out[f"{f}_rate"], out[f"{f}_lo"], out[f"{f}_hi"] = k.values.astype(int), p, lo, hi
    out["thin"] = out.n < min_n
    return out


def barh_rates(tab, flag, title, subtitle, ref=None, order=None, color=O_MID, label_fmt="{:.1%}"):
    """Horizontal bars of a rate with its interval; n= in tick labels; thin groups pale; optional reference line."""
    t = tab if order is None else tab.loc[order]
    t = t.sort_values(f"{flag}_rate")
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(t) + 1.6))
    y = np.arange(len(t)); cols = [O_PALE if th else color for th in t.thin]
    ax.barh(y, t[f"{flag}_rate"], color=cols)
    ax.errorbar(t[f"{flag}_rate"], y, xerr=[t[f"{flag}_rate"] - t[f"{flag}_lo"], t[f"{flag}_hi"] - t[f"{flag}_rate"]], fmt="none", ecolor=BLACK, lw=1, capsize=2)
    for yy, v, hi, k, n in zip(y, t[f"{flag}_rate"], t[f"{flag}_hi"], t[f"{flag}_k"], t.n):
        ax.text(hi + ax.get_xlim()[1] * 0.01, yy, f"{label_fmt.format(v)} ({k:,}/{n:,})", va="center", fontsize=8)
    ax.set_yticks(y, [f"{i} (n={n:,})" for i, n in zip(t.index, t.n)], fontsize=8.5)
    if ref is not None:
        ax.axvline(ref, color=GRAY, ls="--", lw=1); ax.text(ref, len(t) - 0.4, f" overall {ref:.1%}", color="#666", fontsize=7.5)
    ax.grid(axis="x"); ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    titled(ax, title, subtitle)
    return fig


def arm_table(df, arm, outcomes, treat=0):
    """Two-arm means with 95% t-intervals on the difference, per outcome. `treat` is the arm value that got the feature."""
    rows = []
    for y in outcomes:
        a, b = df.loc[df[arm] == treat, y].dropna(), df.loc[df[arm] != treat, y].dropna()
        diff = a.mean() - b.mean(); se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        rows.append(dict(outcome=y, n_on=len(a), n_holdout=len(b), mean_on=a.mean(), mean_holdout=b.mean(), diff=diff, lo=diff - 1.96 * se, hi=diff + 1.96 * se,
                         rel=diff / b.mean() if b.mean() else np.nan, p=2 * st.norm.sf(abs(diff / se)) if se > 0 else np.nan))
    return pd.DataFrame(rows).set_index("outcome")


def plot_arms(tab, title, subtitle, rel=True):
    """Horizontal bars: relative (or absolute) effect per outcome with its interval; zero line in grey."""
    t = tab.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(t) + 1.6))
    y = np.arange(len(t))
    if rel:
        v = t.rel; lo = t.lo / t.mean_holdout; hi = t.hi / t.mean_holdout; fmt = "{:+.1%}"
    else:
        v = t["diff"]; lo = t.lo; hi = t.hi; fmt = "{:+.3f}"
    sig = (lo > 0) | (hi < 0)
    ax.barh(y, v, color=[O_MID if s_ else O_PALE for s_ in sig])
    ax.errorbar(v, y, xerr=[v - lo, hi - v], fmt="none", ecolor=BLACK, lw=1, capsize=2)
    for yy, vv, hh in zip(y, v, hi):
        ax.text(max(hh, 0) + 0.002, yy, fmt.format(vv), va="center", fontsize=8)
    ax.axvline(0, color=GRAY, lw=1)
    ax.set_yticks(y, [f"{i} (n={a:,}/{b:,})" for i, a, b in zip(t.index, t.n_on, t.n_holdout)], fontsize=8.5)
    ax.grid(axis="x")
    if rel:
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:+.0%}"))
    titled(ax, title, subtitle)
    return fig


def mde_table(p0, n_treat_list, share_control, alpha=0.05, power=0.8):
    """Minimum detectable difference in a proportion, two-sided, for a treated size and a control share of the base."""
    za, zb = st.norm.ppf(1 - alpha / 2), st.norm.ppf(power)
    rows = []
    for n_t in n_treat_list:
        for sc in share_control:
            n_c = n_t * sc / (1 - sc)
            se = np.sqrt(p0 * (1 - p0) * (1 / n_t + 1 / n_c))
            rows.append(dict(n_treated=n_t, control_share=sc, n_control=int(n_c), mde_pp=(za + zb) * se * 100))
    return pd.DataFrame(rows)


def close_md(game, headline, go, action, guardrail, revisit):
    return (f"### {game} — close\n\n**Headline:** {headline}\n\n**Go / No-go:** {go}\n\n**Action:** {action}\n\n"
            f"**Guardrail:** {guardrail}\n\n**Revisit:** {revisit}")


# ------------------------------------------------------------------ synthetic control (one treated unit, a donor pool)
def synth_weights(y_treated_pre, Y_donors_pre):
    """Non-negative weights summing to 1 that best reproduce the treated pre-period series from the donors (SLSQP on the
    simplex; falls back to NNLS + normalise). Returns (weights Series, pre RMSPE)."""
    from scipy.optimize import minimize, nnls
    Y = np.asarray(Y_donors_pre, float); y = np.asarray(y_treated_pre, float)
    k = Y.shape[1]
    w0, _ = nnls(Y, y); w0 = w0 / w0.sum() if w0.sum() > 0 else np.full(k, 1 / k)
    res = minimize(lambda w: np.mean((Y @ w - y) ** 2), w0, bounds=[(0, 1)] * k, constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}], method="SLSQP")
    w = res.x if res.success else w0
    w = np.clip(w, 0, None); w = w / w.sum()
    rmspe = float(np.sqrt(np.mean((Y @ w - y) ** 2)))
    return pd.Series(w, index=Y_donors_pre.columns), rmspe


def synth_control(wide, treated, donors, launch, fit_start=None, smooth=7, index=True):
    """wide: date-indexed frame, one column per game (a daily metric). Fits weights on [fit_start, launch) after a rolling-mean
    smooth, returns dict(path: DataFrame[treated, synthetic, gap], weights, rmspe_pre, rmspe_post, effect = mean gap over POST /
    synthetic mean over POST). index=True divides every series by its own fit-window mean first (demeaned synthetic control):
    simplex weights cannot scale a donor up or down, so levels must be matched by indexing, and the path is then in index units."""
    s = wide.rolling(smooth, min_periods=max(1, smooth // 2)).mean().dropna()
    fit_start = fit_start or (launch - D(FIT))
    if index:
        base = s[(s.index >= fit_start) & (s.index < launch)].mean()
        s = s / base
    pre = s[(s.index >= fit_start) & (s.index < launch)]
    w, rm_pre = synth_weights(pre[treated], pre[donors])
    synth = s[donors] @ w
    path = pd.DataFrame({"treated": s[treated], "synthetic": synth}); path["gap"] = path.treated - path.synthetic
    post = path[(path.index >= launch + D(RAMP)) & (path.index < launch + D(RAMP + POST))]
    rm_post = float(np.sqrt(np.mean(post.gap ** 2)))
    return dict(path=path, weights=w, rmspe_pre=rm_pre, rmspe_post=rm_post, effect=post.gap.mean() / post.synthetic.mean(),
                gap_post=post.gap.mean(), ratio=rm_post / rm_pre if rm_pre > 0 else np.nan)


def placebo_in_space(wide, treated, donors, launch, **kw):
    """Run synth_control with each donor as the fake treated unit (remaining donors + the real treated excluded as donors).
    Returns a table of post/pre RMSPE ratios and effects; the real unit's rank among them is the permutation p-value."""
    rows = []
    for fake in donors:
        pool = [g for g in donors if g != fake]
        r = synth_control(wide, fake, pool, launch, **kw)
        rows.append(dict(unit=fake, effect=r["effect"], rmspe_pre=r["rmspe_pre"], rmspe_post=r["rmspe_post"], ratio=r["ratio"], placebo=True))
    r = synth_control(wide, treated, donors, launch, **kw)
    rows.append(dict(unit=treated, effect=r["effect"], rmspe_pre=r["rmspe_pre"], rmspe_post=r["rmspe_post"], ratio=r["ratio"], placebo=False))
    t = pd.DataFrame(rows).sort_values("ratio", ascending=False).reset_index(drop=True)
    t["rank"] = np.arange(1, len(t) + 1)
    return t


def plot_synth(r, launch, name, metric_label):
    p = r["path"]
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw=dict(height_ratios=[2, 1]))
    ax = axes[0]
    ax.plot(p.index, p.treated, color=BLACK, lw=1.8, label=f"{name} (observed)")
    ax.plot(p.index, p.synthetic, color=O_MID, lw=1.8, ls="--", label="synthetic (weighted donors)")
    ax.axvline(launch, color=GRAY, ls="--", lw=1); ax.axvspan(launch + D(RAMP), launch + D(RAMP + POST), color=O_PALE, alpha=.5, lw=0)
    ax.legend(fontsize=8, loc="upper left")
    titled(ax, f"{name}: observed vs synthetic control — {metric_label}",
           f"weights fit on {FIT} pre-launch days (7-day smoothed) · pre RMSPE {r['rmspe_pre']:.3f} · POST effect {r['effect']:+.1%} · orange band = POST window")
    ax = axes[1]
    ax.plot(p.index, p.gap, color=O_DARK, lw=1.4); ax.axhline(0, color=GRAY, lw=.8); ax.axvline(launch, color=GRAY, ls="--", lw=1)
    ax.set_ylabel("gap (obs − synth)")
    ax.xaxis.set_major_locator(mdates.MonthLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.tight_layout()
    return fig


# ------------------------------------------------------------------ sensitivity to an unmeasured confounder
def evalue(rr):
    """E-value (VanderWeele & Ding): the minimum strength of association, on the risk-ratio scale, that an unmeasured confounder
    would need with both treatment and outcome to explain away an observed risk ratio `rr`."""
    rr = float(rr); rr = 1 / rr if rr < 1 else rr
    return rr + np.sqrt(rr * (rr - 1)) if rr > 1 else 1.0


# ------------------------------------------------------------------ power for counts and clustered designs
def mde_grid(p0, n_total, holdout_shares, weeks, weekly_frac, icc=(0.0,), cluster_size=1, alpha=0.05, power=0.8, sd=None):
    """Minimum detectable difference for a rate (sd=None → binomial) or a count (sd given), across holdout share × weeks × ICC.
    n_total = eligible population; weekly_frac = share of it that becomes observable per week (cohort accrual);
    design effect = 1 + (cluster_size − 1)·ICC for party/lobby randomization."""
    za, zb = st.norm.ppf(1 - alpha / 2), st.norm.ppf(power)
    rows = []
    for wk in weeks:
        n = n_total * min(1.0, weekly_frac * wk)
        for sc in holdout_shares:
            n_c, n_t = n * sc, n * (1 - sc)
            for ic in icc:
                deff = 1 + (cluster_size - 1) * ic
                var = (sd ** 2 if sd is not None else p0 * (1 - p0)) * (1 / n_t + 1 / n_c) * deff
                mde = (za + zb) * np.sqrt(var)
                rows.append(dict(weeks=wk, holdout_share=sc, icc=ic, n_treated=int(n_t), n_control=int(n_c), design_effect=deff,
                                 mde=mde, mde_rel=mde / p0 if p0 else np.nan))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ sizing dials
def dials_table(cands, dials, haircuts=None):
    """cands: DataFrame indexed by candidate with the dial columns; dials: ordered list of column names multiplied together;
    haircuts: {col: factor} applied after. Returns the frame with a `prize` column and each step's running product."""
    out = cands.copy(); run = np.ones(len(out))
    for c in dials:
        run = run * out[c].values; out[f"after_{c}"] = run
    for c, f in (haircuts or {}).items():
        run = run * (1 - out[c].values * f) if c in out else run * f; out[f"after_{c}_haircut"] = run
    out["prize"] = run
    return out.sort_values("prize", ascending=False)
