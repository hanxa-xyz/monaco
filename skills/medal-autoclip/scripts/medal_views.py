"""Views, estimates and the draft close for the auto-clipping case.

Method (say it out loud once, then just point at the numbers):
- Windows: PRE = 28 days before launch. POST = days 14–41 after launch (skip the 2-week rollout ramp).
- Naive = POST mean / PRE mean − 1.
- ITS (interrupted time series) = fit log(metric) ~ level [+ trend] + day-of-week on the 56 days before
  launch, project it over POST; lift = actual / projected − 1. Level vs trend is picked by a backtest on
  the last 2 pre-launch weeks (trend must clearly win — extrapolating a slope is the riskier call).
- 95% CI = prediction error of the projected baseline + noise in the POST mean, inflated for day-to-day
  autocorrelation. CI excludes 0 and |lift| ≥ 3% → UP/DOWN; excludes 0 but small → "small ±".
- Per-player rates are the read on clip behaviour: they net out player-count swings from seasons,
  esports events and summer. Player counts are the confounded metric, so they never carry the verdict alone.
- Spike days (bulk deletions of old clips, sales / discounts) are detected and excluded from fits.
"""
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from monaco import viz as dv  # noqa: E402

from medal_parse import GAMES  # noqa: E402

PRE_DAYS, RAMP, POST_DAYS, FIT_DAYS = 28, 14, 28, 56
D = lambda n: pd.Timedelta(days=n)  # noqa: E731

# metric, label, role — order = scorecard order
METRICS = [
    ("players", "Medal players in game", "studio (confounded)"),
    ("clips_total", "Clips captured, all", "data volume"),
    ("clips_manual", "Manual (hotkey) clips", "data volume"),
    ("manual_pp", "Manual clips / player", "cannibalization"),
    ("pct_clipping", "% players with ≥1 clip", "mechanical"),
    ("shares", "Clips shared off-Medal", "engagement"),
    ("shares_pp", "Shares / player", "engagement"),
    ("pct_sharing", "% players sharing", "engagement"),
    ("share_per_clip", "Shares / clip", "dilution"),
    ("posts_pp", "Public posts / player", "engagement"),
    ("deletes_pp", "Deletions / player (client, any-age)", "curation burden"),
    ("pct_deleting", "% players deleting", "curation burden"),
]
LABEL = {m: lbl for m, lbl, _ in METRICS}


# ---------------------------------------------------------------- prep
def derive(daily):
    d = daily.sort_values("date").drop_duplicates("date").set_index("date").asfreq("D")
    g = lambda c: d[c].fillna(0) if c in d else 0  # noqa: E731
    d["clips_manual"] = d["clips_total"] - g("clips_autoclip_native") - g("clips_autoclip_steam_achievement")
    d["clips_auto"] = g("clips_autoclip_native") + g("clips_autoclip_steam_achievement")
    p = d["players"].replace(0, np.nan)
    d["manual_pp"] = d["clips_manual"] / p
    d["auto_pp"] = d["clips_auto"] / p
    d["pct_clipping"] = d.get("clippers_total") / p if "clippers_total" in d else np.nan
    d["shares"] = d.get("clips_shared_distinct", np.nan)
    d["shares_pp"] = d["shares"] / p
    d["pct_sharing"] = d["users_sharing"] / p if "users_sharing" in d else np.nan
    d["share_per_clip"] = d["shares"] / d["clips_total"].replace(0, np.nan)
    d["posts_pp"] = d["public_posts_total"] / p if "public_posts_total" in d else np.nan
    d["deletes_pp"] = d["clips_deleted_distinct"] / p if "clips_deleted_distinct" in d else np.nan
    d["pct_deleting"] = d["users_deleting"] / p if "users_deleting" in d else np.nan
    return d


def spikes(s, window=21, ratio=1.15, z=5.0, pad=1, run_z=2.5, run_len=3):
    """Days far above a centered rolling median (robust z on the day-of-week-adjusted log ratio): one day
    beyond z, or a run of ≥run_len consecutive days beyond run_z (a multi-day purge or sale).
    The window must be > 2× the longest spike you want caught (a 15-day sale needs ~61)."""
    s = s.astype(float)
    med = s.rolling(window, center=True, min_periods=window // 2).median()
    lr = np.log(s.clip(lower=1e-9) / med)
    lr = lr - lr.groupby(lr.index.dayofweek).transform("median")
    mad = (lr - lr.median()).abs().median() * 1.4826 or 1e-9
    zz = (lr - lr.median()) / mad
    big = lr > np.log(1 + (ratio - 1) / 2)
    m = (lr > np.log(ratio)) & (zz > z)
    elevated = (zz > run_z) & big
    run_id = (~elevated).cumsum()
    run_size = elevated.groupby(run_id).transform("sum")
    m = m | (elevated & (run_size >= run_len))
    for _ in range(pad):
        m = m | m.shift(1, fill_value=False) | m.shift(-1, fill_value=False)
    return m.fillna(False)


def spans(mask):
    """[(start, end)] runs of True."""
    out, start = [], None
    for day, v in mask.items():
        if v and start is None:
            start = day
        if not v and start is not None:
            out.append((start, prev))
            start = None
        prev = day
    if start is not None:
        out.append((start, prev))
    return out


# ---------------------------------------------------------------- estimators
def _design(idx, t0, trend=True):
    t = (idx - t0).days.values.astype(float)
    dow = np.eye(7)[idx.dayofweek.values][:, 1:]
    return np.column_stack([np.ones(len(idx)), t, dow] if trend else [np.ones(len(idx)), dow])



def _mask(exclude, idx):
    return exclude.reindex(idx, fill_value=False).astype(bool) if exclude is not None else pd.Series(False, idx)


def _fit(s, start, end, exclude, trend, t0):
    w = s[(s.index >= start) & (s.index < end)]
    w = w[(w > 0) & w.notna() & ~_mask(exclude, w.index)]
    if len(w) < 21:
        return None
    X, y = _design(w.index, t0, trend), np.log(w.values)
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    e = y - X @ beta
    rho = pd.Series(e).autocorr(1)
    rho = 0.0 if np.isnan(rho) else float(np.clip(rho, 0, 0.9))
    return dict(beta=beta, XtX_inv=XtX_inv, s2=e @ e / max(len(y) - X.shape[1], 1),
                infl=(1 + rho) / (1 - rho), trend=trend, t0=t0)


def _predict(f, idx):
    X = _design(idx, f["t0"], f["trend"])
    return X @ f["beta"], X


def choose_model(s, launch, exclude=None):
    """Level vs trend: fit each on the 8 weeks ending 2 weeks before launch, score on the last 2 pre-launch
    weeks. Trend must win by >1pt of error to be used (extrapolating a slope is the riskier call)."""
    hold = launch - D(14)
    h = s[(s.index >= hold) & (s.index < launch)]
    h = h[(h > 0) & h.notna() & ~_mask(exclude, h.index)]
    errs = {}
    for trend in (False, True):
        f = _fit(s, hold - D(FIT_DAYS), hold, exclude, trend, hold)
        if f is not None and len(h) >= 7:
            yhat, _ = _predict(f, h.index)
            errs[trend] = abs(np.log(h.sum() / np.exp(yhat + f["s2"] / 2).sum()))
    use_trend = len(errs) == 2 and errs[True] < errs[False] - 0.01
    return use_trend, errs


def its(s, launch, exclude=None, horizon=RAMP + POST_DAYS, trend=True):
    """Interrupted time series on log(metric): baseline (level or trend, + weekday) fit on the 56 pre-launch
    days, projected over POST. 95% CI = prediction error of the projected mean + noise in the POST mean,
    inflated for day-to-day autocorrelation."""
    s = s.astype(float)
    f = _fit(s, launch - D(FIT_DAYS), launch, exclude, trend, launch)
    post = s.reindex(pd.date_range(launch + D(RAMP), launch + D(RAMP + POST_DAYS - 1)))
    post = post[post.notna() & (post > 0) & ~_mask(exclude, post.index)]
    if f is None or len(post) < 7:
        return None
    yhat, Xp = _predict(f, post.index)
    cf_post = np.exp(yhat + f["s2"] / 2)
    log_lift = np.log(post.sum() / cf_post.sum())
    xbar = Xp.mean(0)
    se = np.sqrt(f["s2"] * f["infl"] * (xbar @ f["XtX_inv"] @ xbar + 1 / len(post)))
    full = pd.date_range(launch, launch + D(horizon - 1))
    yf, _ = _predict(f, full)
    return dict(lift=np.exp(log_lift) - 1, ci=(np.exp(log_lift - 1.96 * se) - 1, np.exp(log_lift + 1.96 * se) - 1),
                cf=pd.Series(np.exp(yf + f["s2"] / 2), full), cf_post_mean=cf_post.mean(), post_mean=post.mean())


def placebo_band(s, launch, exclude=None, step=7, trend=False):
    """Diagnostic for live use: lifts at fake launch dates before the real one (5th/50th/95th pct).
    Only meaningful when the pre-period is in the same regime (not during a launch decay)."""
    first = s.first_valid_index()
    pre = s[s.index < launch]
    starts = pd.date_range(first + D(FIT_DAYS), launch - D(RAMP + POST_DAYS), freq=f"{step}D")
    lifts = [r["lift"] for L in starts if (r := its(pre, L, exclude, trend=trend))]
    return np.percentile(lifts, [5, 50, 95]) if len(lifts) >= 3 else None


def window_means(s, launch, exclude=None):
    ex = (exclude if exclude is not None else pd.Series(False, s.index)).reindex(s.index, fill_value=False)
    s = s[~ex]
    pre = s[(s.index >= launch - D(PRE_DAYS)) & (s.index < launch)].mean()
    post = s[(s.index >= launch + D(RAMP)) & (s.index < launch + D(RAMP + POST_DAYS))].mean()
    return pre, post


MATERIAL = 0.03   # a CI that excludes 0 but a lift under 3% is "small", not a headline


def assess(s, launch, exclude=None, trend=None):
    pre, post = window_means(s, launch, exclude)
    errs = {}
    if trend is None:
        trend, errs = choose_model(s, launch, exclude)
    r = its(s, launch, exclude, trend=trend) if pre and pre > 0 else None
    if r is None:
        call = "new (no pre)" if (pre == 0 or pd.isna(pre)) and post else "n/a"
        lift, lo, hi = np.nan, np.nan, np.nan
    else:
        lift, (lo, hi) = r["lift"], r["ci"]
        sig = lo > 0 or hi < 0
        call = "within noise" if not sig else ("UP" if lift > 0 else "DOWN") if abs(lift) >= MATERIAL else \
            ("small +" if lift > 0 else "small −")
    return dict(pre=pre, post=post, naive=post / pre - 1 if pre else np.nan, its=lift, ci_lo=lo, ci_hi=hi,
                trend=trend, backtest=errs, call=call, cf=r["cf"] if r else None,
                incr_per_day=(r["post_mean"] - r["cf_post_mean"]) if r else np.nan)


# ---------------------------------------------------------------- game analysis
def analyze_daily(daily, launch):
    d = derive(daily)
    purge = spikes(d["deletes_pp"]) if "deletes_pp" in d and d["deletes_pp"].notna().any() else pd.Series(False, d.index)
    purge = purge & (d["clips_deleted_distinct"] > 0)
    res = {}
    for m, _, _ in METRICS:
        if m in d and d[m].notna().sum() > 30:
            res[m] = assess(d[m], launch, purge if m.startswith(("deletes", "pct_deleting")) else None)
    return d, res, purge


def scorecard(res):
    rows = []
    for m, lbl, role in METRICS:
        if m not in res:
            continue
        r = res[m]
        rows.append(dict(metric=lbl, role=role, pre=r["pre"], post=r["post"], naive=r["naive"],
                         vs_baseline=r["its"], ci95=_band(r), call=r["call"], model="trend" if r["trend"] else "level"))
    return pd.DataFrame(rows)


def _band(r):
    return "" if np.isnan(r["ci_lo"]) else f"{r['ci_lo']:+.1%} … {r['ci_hi']:+.1%}"


def fmt_scorecard(sc):
    out = sc.copy()
    pct_metrics = {"% players with ≥1 clip", "% players sharing", "Shares / clip", "% players deleting"}
    for c in ("pre", "post"):
        out[c] = [f"{v:.1%}" if m in pct_metrics else (f"{v:,.2f}" if abs(v) < 20 else f"{v:,.0f}")
                  if pd.notna(v) else "" for m, v in zip(out["metric"], out[c])]
    for c in ("naive", "vs_baseline"):
        out[c] = [f"{v:+.1%}" if pd.notna(v) else "" for v in out[c]]
    return out


def outcomes_14d(o14, launch):
    if o14 is None:
        return None
    o = o14.copy()
    launch_week = launch - D(launch.dayofweek)
    o["period"] = np.where(o["week"] < launch_week, "pre", np.where(o["week"] == launch_week, "launch wk", "post"))
    g = o[o["period"] != "launch wk"].groupby(["trigger_class", "period"])[
        ["clips_captured", "deleted_within_14d", "shared_within_14d", "public_posts"]].sum()
    for k in ("deleted_within_14d", "shared_within_14d", "public_posts"):
        g[k.split("_")[0] + "_rate"] = g[k] / g["clips_captured"]
    g = g.rename(columns={"public_rate": "post_rate"})
    post = g.xs("post", level="period") if "post" in g.index.get_level_values("period") else g.iloc[:0]
    tot = post[["clips_captured", "shared_within_14d"]].sum()
    post = post.assign(pct_of_clips=post["clips_captured"] / tot["clips_captured"],
                       pct_of_shares=post["shared_within_14d"] / tot["shared_within_14d"])
    return dict(table=g.reset_index(), post=post, launch_week=launch_week.date())


def triggers(tb):
    if tb is None:
        return None
    t = tb.copy()
    t["delete_rate"] = t["deleted_within_14d"] / t["clips_captured"]
    t["share_rate"] = t["shared_within_14d"] / t["clips_captured"]
    t["post_rate"] = t["public_posts"] / t["clips_captured"]
    t["pct_volume"] = t["clips_captured"] / t["clips_captured"].sum()
    t["pct_shares"] = t["shared_within_14d"] / t["shared_within_14d"].sum()
    t["pct_deletes"] = t["deleted_within_14d"] / t["deleted_within_14d"].sum()
    avg_s = t["shared_within_14d"].sum() / t["clips_captured"].sum()
    avg_d = t["deleted_within_14d"].sum() / t["clips_captured"].sum()
    t["verdict"] = np.select(
        [(t["share_rate"] >= avg_s) & (t["delete_rate"] <= avg_d),
         (t["share_rate"] < 0.6 * avg_s) & (t["delete_rate"] > avg_d)],
        ["keeper", "junk"], "middling")
    t = t.sort_values("share_rate", ascending=False).reset_index(drop=True)
    junk = t[t["verdict"] == "junk"]
    prune = dict(triggers=list(junk["trigger_name"]), vol=junk["pct_volume"].sum(),
                 deletes=junk["pct_deletes"].sum(), shares=junk["pct_shares"].sum())
    return dict(table=t, avg_share=avg_s, avg_delete=avg_d, prune=prune)


def return_rate(rr):
    if rr is None or "got_autoclip" not in rr:
        return None
    r = rr.groupby("got_autoclip")[["players", "returned_wk2", "returned_wk5"]].sum()
    r["wk2"] = r["returned_wk2"] / r["players"]
    r["wk5"] = r["returned_wk5"] / r["players"]
    gap2 = r.loc[True, "wk2"] - r.loc[False, "wk2"] if {True, False} <= set(r.index) else np.nan
    gap5 = r.loc[True, "wk5"] - r.loc[False, "wk5"] if {True, False} <= set(r.index) else np.nan
    return dict(table=r.reset_index(), gap_wk2=gap2, gap_wk5=gap5)


def external(ext, d, launch):
    if ext is None:
        return None
    e = ext.drop_duplicates("date").set_index("date").asfreq("D")
    none = pd.Series(False, e.index)
    sale = spikes(e["copies_sold"], window=61, ratio=1.6, z=4.0) if "copies_sold" in e else none
    dau_spike = (spikes(e["dau"], window=61, ratio=1.15, z=4.0) & ~sale) if "dau" in e else none
    excl = sale | dau_spike
    res = {}
    for m in ("dau", "ccu_avg", "ccu_peak", "copies_sold", "wishlists"):
        if m in e and e[m].notna().sum() > 30:
            res[m] = assess(e[m], launch, excl)
    # Net of the whole-game shock: wishlists / copies per DAU. Patches, seasons, summer and a misfit trend lift
    # DAU and the funnel together; Medal's channel (shares → strangers wishlisting/buying) barely moves DAU.
    if "dau" in e:
        for m in ("wishlists", "copies_sold"):
            if m in e:
                net = (e[m] / e["dau"]).rename(f"{m}_per_dau")
                res[net.name] = assess(net, launch, excl)
    pen = None
    if "dau" in e:
        p = (d["players"] / e["dau"]).dropna().rename("medal_per_dau")
        pen = window_means(p, launch)
        # Medal's own player lift for a game whose DAU is moving: penetration, not the raw count
        res["medal_per_dau"] = assess(p, launch, excl)

    def ratio_of(col, a, b):
        base = e[col].rolling(61, center=True, min_periods=20).median().loc[a:b].mean()
        return e.loc[a:b, col].mean() / base
    sale_spans = [(a.date(), b.date(), ratio_of("copies_sold", a, b)) for a, b in spans(sale)]
    dau_spans = [(a.date(), b.date(), ratio_of("dau", a, b)) for a, b in spans(dau_spike)]

    # Weekly residual vs projected trend, next to Medal's auto-clip share volume: a Medal-driven lift should
    # track the share ramp; a lift that jumps in one week with flat shares is something else (patch, sale, event).
    wk = {}
    for m in ("dau", "wishlists", "copies_sold"):
        if m in res and res[m]["cf"] is not None:
            cf = res[m]["cf"]
            wk[f"{m} vs trend"] = (e[m].reindex(cf.index) / cf).resample("W-SUN").mean() - 1
    if wk:
        weekly = pd.DataFrame(wk)
        native = d.get("clips_autoclip_native")
        if native is not None:
            weekly["medal auto-clips/wk"] = native.reindex(weekly.index.union(native.index)).resample("W-SUN").sum() \
                .reindex(weekly.index)
        weekly["sale/spike days"] = excl.reindex(e.index).resample("W-SUN").sum().reindex(weekly.index)
        weekly.index = weekly.index.date
    else:
        weekly = None
    return dict(e=e, res=res, sale=sale, dau_spike=dau_spike, excl=excl, sale_spans=sale_spans,
                dau_spans=dau_spans, penetration=pen, weekly=weekly)


# Plausibility ceilings for the Medal → studio channel (judgment, say them out loud): a shared clip reaches a
# handful of friends / a Discord channel, so >0.5 copies or >2 wishlists per incremental share is implausible,
# and a DAU lift larger than half of Medal's own player base in the game can't come from Medal users.
MAX_COPIES_PER_SHARE, MAX_WISHLISTS_PER_SHARE, MAX_DAU_FRAC_OF_MEDAL = 0.5, 2.0, 0.5


def plausibility(A):
    x, be = A["ext"], A["break_even"] or {}
    if not x:
        return None
    flags = []
    medal_post = A["res"]["players"]["post"] if "players" in A["res"] else np.nan
    c = be.get("implied_copies_per_share")
    if _net(x, "copies_sold").get("call") == "UP" and c and c > MAX_COPIES_PER_SHARE:
        flags.append(f"net copies lift implies {c:.1f} copies per auto-clip share (ceiling {MAX_COPIES_PER_SHARE})")
    w = be.get("implied_wishlists_per_share")
    if _net(x, "wishlists").get("call") == "UP" and w and w > MAX_WISHLISTS_PER_SHARE:
        flags.append(f"net wishlist lift implies {w:.1f} wishlists per auto-clip share (ceiling {MAX_WISHLISTS_PER_SHARE})")
    return flags


def dau_shock(A):
    """DAU up by more than Medal's own players could cause → a whole-game shock is moving the studio metrics."""
    x = A["ext"]
    if not x or "dau" not in x["res"] or x["res"]["dau"]["call"] != "UP":
        return None
    inc, medal = x["res"]["dau"]["incr_per_day"], A["res"]["players"]["post"] if "players" in A["res"] else np.nan
    return f"DAU is up ~{inc:,.0f}/day vs baseline while only ~{medal:,.0f} Medal users play per day" \
        if inc > MAX_DAU_FRAC_OF_MEDAL * medal else None


def _net(x, m):
    """The per-DAU assessment if available, else the raw one."""
    return x["res"].get(f"{m}_per_dau") or x["res"].get(m) or {}


def analyze_game(P, game, launch=None):
    g = GAMES[game]
    launch = pd.Timestamp(launch or g["launch"])
    daily = P.get(game, "daily")
    if daily is None:
        return None
    d, res, purge = analyze_daily(daily, launch)
    A = dict(game=game, name=g["name"], model=g["model"], launch=launch, d=d, res=res, purge=purge,
             purge_spans=[(a.date(), b.date()) for a, b in spans(purge)],
             sc=scorecard(res), o14=outcomes_14d(P.get(game, "outcomes_14d"), launch),
             trig=triggers(P.get(game, "trigger_breakdown")), rr=return_rate(P.get(game, "return_rate")),
             ext=external(P.ext(game), d, launch))
    post = d[(d.index >= launch + D(RAMP)) & (d.index < launch + D(RAMP + POST_DAYS))]
    A["auto_per_day"] = post["clips_auto"].mean()
    A["auto_share_of_clips"] = post["clips_auto"].sum() / post["clips_total"].sum()
    A["native_per_day"] = post.get("clips_autoclip_native", pd.Series(dtype=float)).mean()
    A["break_even"] = _break_even(A)
    A["implausible"] = plausibility(A)
    A["dau_shock"] = dau_shock(A)
    lo, hi = launch + D(RAMP), launch + D(RAMP + POST_DAYS - 1)
    A["events_in_post"] = [lbl for s, e, lbl in g.get("events", [])
                           if pd.Timestamp(s) <= hi and pd.Timestamp(e) >= lo]
    if A["ext"]:
        A["events_in_post"] += [f"sale-like copies spike {a:%b %d}–{b:%b %d}" for a, b, _ in A["ext"]["sale_spans"]
                                if pd.Timestamp(a) <= hi and pd.Timestamp(b) >= lo]
        A["events_in_post"] += [f"DAU spike {a:%b %d}–{b:%b %d} (patch/event?)" for a, b, _ in A["ext"]["dau_spans"]
                                if pd.Timestamp(a) <= hi and pd.Timestamp(b) >= lo]
    A["close"] = draft_close(A)
    return A


def _break_even(A):
    """GJ-style: how many copies per incremental auto-clip share would the data need to see a lift?"""
    x, o = A["ext"], A["o14"]
    if not x or "copies_sold" not in x["res"] or o is None or "autoclip_native" not in o["post"].index:
        return None
    share_rate = o["post"].loc["autoclip_native", "shared_rate"]
    shares_day = A["native_per_day"] * share_rate
    r = x["res"]["copies_sold"]
    cf = r["cf"]
    cf_day = cf[(cf.index >= A["launch"] + D(RAMP))].mean() if cf is not None else np.nan
    out = dict(auto_shares_per_day=shares_day, copies_cf_per_day=cf_day)
    half = (r["ci_hi"] - r["ci_lo"]) / 2 if not np.isnan(r["ci_lo"]) else np.nan
    if shares_day and not np.isnan(half):
        out["copies_per_share_to_detect"] = half * cf_day / shares_day
    if shares_day and pd.notna(_net(x, "copies_sold").get("its")):
        out["implied_copies_per_share"] = _net(x, "copies_sold")["its"] * cf_day / shares_day
    if shares_day and cf_day:
        out["copies_ceiling_pct"] = MAX_COPIES_PER_SHARE * shares_day / cf_day
    if "wishlists" in x["res"] and shares_day:
        w = x["res"]["wishlists"]
        wcf = w["cf"][(w["cf"].index >= A["launch"] + D(RAMP))].mean() if w["cf"] is not None else np.nan
        wn = _net(x, "wishlists")
        out["implied_wishlists_per_share"] = wn["its"] * wcf / shares_day if pd.notna(wn.get("its")) else np.nan
        out["wishlists_ceiling_pct"] = MAX_WISHLISTS_PER_SHARE * shares_day / wcf if wcf else np.nan
        out["wishlists_per_share_to_detect"] = (w["ci_hi"] - w["ci_lo"]) / 2 * wcf / shares_day \
            if not np.isnan(w["ci_lo"]) else np.nan
    return out


# ---------------------------------------------------------------- draft close
def _p(x, signed=True):
    return "n/a" if x is None or pd.isna(x) else (f"{x:+.0%}" if signed else f"{x:.0%}")


def _call(A, m):
    r = A["res"].get(m)
    return (r["its"], r["call"], _band(r)) if r else (np.nan, "n/a", "")


def draft_close(A):
    name, res = A["name"], A["res"]
    man, man_call, man_band = _call(A, "manual_pp")
    shp, shp_call, _ = _call(A, "shares_pp")
    spc = res.get("share_per_clip", {})
    dpp, dpp_call, _ = _call(A, "deletes_pp")
    trig, o, rr, x = A["trig"], A["o14"], A["rr"], A["ext"]
    cannibal = man_call == "DOWN" and man < -0.05
    engaged = shp_call != "DOWN"

    lines = []
    implausible = A.get("implausible") or []
    if A["model"] == "paid" and x:
        raw_up = any((x["res"].get(m) or {}).get("call") == "UP" for m in ("copies_sold", "wishlists"))
        net_up = [m for m in ("wishlists", "copies_sold") if (x["res"].get(f"{m}_per_dau") or {}).get("call") == "UP"]
        if not engaged:
            verdict = "ITERATE"
        elif net_up and not implausible:
            verdict = (f"GO — and a studio case study: {' and '.join(m.replace('_sold', '') for m in net_up)} grew "
                       f"faster than the game's own DAU")
        elif net_up:
            verdict = "GO for Medal; the studio lift is too big for Medal's reach — find the confound before claiming it"
        elif raw_up:
            verdict = "GO for Medal; studio numbers rose with the whole game — Medal's share can't be separated yet"
        else:
            verdict = "GO for Medal; studio impact not measurable yet"
    else:
        verdict = ("GO, with a cannibalization guardrail" if cannibal else "GO") + \
            (" — prune junk triggers" if trig and trig["prune"]["triggers"] else "") if engaged else "ITERATE"
    lines.append(f"**{name} — {verdict}.**")

    because = [f"auto-clipping adds ~{A['auto_per_day']:,.0f} clips/day ({A['auto_share_of_clips']:.0%} of {name} clips)"]
    because.append(f"manual clips per player moved {_p(man)} vs baseline ({man_call.lower()}; 95% CI {man_band})")
    if spc:
        because.append(f"shares per player {_p(shp)} vs baseline ({shp_call.lower()}) even though shares per clip went "
                       f"{spc['pre']:.1%} → {spc['post']:.1%} — dilution, not decline")
    if o is not None and "autoclip_native" in o["post"].index and "hotkey" in o["post"].index:
        n, h = o["post"].loc["autoclip_native"], o["post"].loc["hotkey"]
        because.append(f"14-day: native auto-clips deleted {n['deleted_rate']:.0%} vs {h['deleted_rate']:.0%} hotkey, "
                       f"shared {n['shared_rate']:.1%} vs {h['shared_rate']:.1%}; auto-clips are {n['pct_of_clips']:.0%} "
                       f"of clips and {n['pct_of_shares']:.0%} of shares")
    if x:
        if x["penetration"]:
            because.append(f"Medal reaches only {x['penetration'][1]:.1%} of the game's DAU")
        be = A["break_even"] or {}
        for m, lbl, ceil in (("wishlists", "wishlists", "wishlists_ceiling_pct"), ("copies_sold", "copies sold", "copies_ceiling_pct")):
            r = x["res"].get(m)
            if r:
                because.append(f"{lbl} {_p(r['its'])} vs baseline ({r['call'].lower()}; 95% CI {_band(r)})"
                               + (f" — Medal can plausibly explain at most ~{be[ceil]:+.0%}" if be.get(ceil) else ""))
        if x["sale_spans"]:
            s = ", ".join(f"{a:%b %d}–{b:%b %d} (×{k:.1f})" for a, b, k in x["sale_spans"])
            because.append(f"excluded sale-like spikes in copies: {s}")
        for m, lbl in (("wishlists", "wishlists"), ("copies_sold", "copies")):
            r = x["res"].get(f"{m}_per_dau")
            if r:
                because.append(f"{lbl} per DAU {_p(r['its'])} ({r['call'].lower()}; 95% CI {_band(r)}) — the read net of "
                               f"whole-game swings")
        mp_ = x["res"].get("medal_per_dau")
        if mp_:
            because.append(f"Medal players per game DAU {_p(mp_['its'])} ({mp_['call'].lower()}; 95% CI {_band(mp_)}) — "
                           f"Medal's own lift, net of the game's swings (the raw player count is confounded)")
        if A.get("dau_shock"):
            because.append(f"{A['dau_shock']} — something else lifted the whole game")
        if implausible:
            because.append("reach check fails — " + "; ".join(implausible))
    pl = res.get("players")
    if pl and A["model"] == "f2p":
        ev = A["events_in_post"]
        because.append(f"Medal {name} players {_p(pl['its'])} vs trend ({pl['call'].lower()})" +
                       (f", but {', '.join(ev)} sits in the post window — not attributable; per-player rates are the clean read"
                        if ev else " — the only engagement signal the studio gets from this data; ask for their DAU"))
    elif A["events_in_post"]:
        because.append(f"post window overlaps {', '.join(A['events_in_post'])}")
    head = [because[0]]                                         # data volume
    if A["model"] == "paid" and x and x["res"].get("wishlists_per_dau"):
        head.append(next(b for b in because if b.startswith("wishlists per DAU")))
    else:
        head.append(because[1])                                 # manual clips: cannibalization
    head += [b for b in because if b.startswith("shares per player")][:1]
    lines.append("Because " + "; ".join(head) + ".")
    lines.append("\n".join(f"- {b}" for b in because if b not in head))

    nxt = []
    if trig and trig["prune"]["triggers"]:
        pr = trig["prune"]
        nxt.append(f"turn off {', '.join(pr['triggers'])} — cuts {pr['vol']:.0%} of auto volume and {pr['deletes']:.0%} "
                   f"of auto deletions for {pr['shares']:.0%} of auto shares")
    if trig:
        tt = trig["table"]
        keep = tt.loc[(tt["verdict"] == "keeper") & ~tt["trigger_name"].str.contains("steam", case=False),
                      "trigger_name"].tolist()
        if keep:
            nxt.append(f"lead the studio pitch with {', '.join(keep[:2])}")
    be = A["break_even"]
    if be and be.get("copies_per_share_to_detect") and A["ext"]["res"]["copies_sold"]["call"] != "UP":
        nxt.append(f"to see a sales lift, each auto-clip share (~{be['auto_shares_per_day']:,.0f}/day) would need "
                   f"≥{be['copies_per_share_to_detect']:.2f} copies — push shares (share prompts on the "
                   f"best triggers) before claiming sales impact")
    lines.append("**Next:** " + "; ".join(nxt or ["hold the current trigger set"]) + ".")

    watch = ["manual-clip cannibalization" if cannibal else "manual clips per player",
             f"deletions per player ({_p(dpp)} vs baseline) and storage cost of auto volume"]
    if A["purge_spans"]:
        watch.append("excluded bulk-deletion days " + ", ".join(f"{a:%b %d}–{b:%b %d}" for a, b in A["purge_spans"])
                     + " (any-age deletions — library cleanup, not new auto-clip junk)")
    lines.append("**Watch:** " + "; ".join(watch) + ".")

    rev = "randomized holdout (auto-clip off for 10% of players) to get causal retention"
    if rr and pd.notna(rr["gap_wk2"]):
        rev += (f" — the {rr['gap_wk2'] * 100:+.0f}pp week-2 return gap for auto-clipped players is selection "
                f"(you only get a goal/jump-scare clip if you played a lot that day), not an effect")
    lines.append("**Revisit with:** " + rev + ".")
    return "\n\n".join(lines)


# ---------------------------------------------------------------- charts
def _style():
    dv.apply_style(110)


def _launch(ax, launch):
    ax.axvline(launch, color=dv.GRAY, ls="--", lw=1)
    ax.axvspan(launch, launch + D(RAMP), color=dv.O_PALE, alpha=0.35, lw=0)


def _dates(ax, step=1):
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=step))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))


def fig_composition(A):
    _style()
    d, L = A["d"], A["launch"]
    fig, ax = plt.subplots(figsize=(10, 3.6))
    series = [("clips_manual", "manual (hotkey)", dv.BLACK)]
    if "clips_autoclip_native" in d:
        series.append(("clips_autoclip_native", "native auto-clip", dv.O_MID))
    if "clips_autoclip_steam_achievement" in d:
        series.append(("clips_autoclip_steam_achievement", "Steam-achievement auto-clip", dv.O_LIGHT))
    for c, lbl, col in series:
        s = d[c].rolling(7, min_periods=4).mean()
        ax.plot(s.index, s, color=col, lw=1.8, label=lbl)
        ax.annotate(f"{s.dropna().iloc[-1]:,.0f}", (s.dropna().index[-1], s.dropna().iloc[-1]),
                    xytext=(4, 0), textcoords="offset points", fontsize=8, color=col, va="center")
    _launch(ax, L)
    _dates(ax)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.legend(loc="upper left", fontsize=8)
    dv.titled(ax, f"{A['name']}: where the clips come from",
              "clips captured per day by trigger source, 7-day rolling · dashed = auto-clip launch, shaded = 2-wk ramp")
    return fig


def fig_rates(A, metrics=("manual_pp", "shares_pp", "pct_sharing", "share_per_clip", "deletes_pp", "players")):
    _style()
    d, L, res = A["d"], A["launch"], A["res"]
    metrics = [m for m in metrics if m in res]
    fig, axes = plt.subplots(2, 3, figsize=(12, 6))
    for ax, m in zip(axes.flat, metrics):
        r = res[m]
        s = d[m].rolling(7, min_periods=4).mean()
        ax.plot(s.index, s, color=dv.BLACK, lw=1.4)
        if r["cf"] is not None:
            cf = r["cf"].rolling(7).mean()
            ax.plot(cf.index, cf, color=dv.GRAY, ls=":", lw=1.8)
        ax.axvspan(L - D(PRE_DAYS), L, color="#f0f0f0", lw=0)
        ax.axvspan(L + D(RAMP), L + D(RAMP + POST_DAYS), color=dv.O_PALE, alpha=0.5, lw=0)
        ax.axvline(L, color=dv.GRAY, ls="--", lw=1)
        if m == "deletes_pp" and A["purge"].any():
            for a, b in spans(A["purge"]):
                ax.axvspan(a, b, color=dv.O_DARK, alpha=0.15, lw=0)
        _dates(ax)
        ax.set_title(LABEL[m], loc="left", fontsize=9.5, fontweight="bold", pad=15)
        ax.text(0, 1.015, f"vs {'trend' if r['trend'] else 'baseline'} {_p(r['its'])} · {r['call']} · CI {_band(r)}",
                transform=ax.transAxes, fontsize=7.8, va="bottom", ha="left",
                color=dv.O_DARK if r["call"] in ("UP", "DOWN") else "#666")
    for ax in list(axes.flat)[len(metrics):]:
        ax.axis("off")
    fig.suptitle(f"{A['name']}: per-player behaviour vs pre-launch trend", x=0.01, ha="left", fontweight="bold")
    fig.text(0.01, 0.94, "black = 7-day rolling actual · dotted gray = baseline from 8 pre-launch weeks (level or trend, picked by backtest) · "
             "gray band = PRE window, orange = POST window", fontsize=8, color="#666")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return fig


def fig_quality(A):
    _style()
    o, t = A["o14"], A["trig"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8), gridspec_kw=dict(width_ratios=[1, 1.3]))
    if o is not None:
        p = o["post"]
        y = np.arange(len(p))
        for k, (col, lbl, c) in enumerate([("deleted_rate", "deleted ≤14d", dv.O_DARK),
                                           ("shared_rate", "shared ≤14d", dv.BLACK),
                                           ("post_rate", "posted public", dv.O_LIGHT)]):
            ax = axes[0]
            ax.barh(y + (k - 1) * 0.26, p[col], height=0.25, color=c, label=lbl)
            for yy, v in zip(y, p[col]):
                ax.text(v, yy + (k - 1) * 0.26, f" {v:.1%}", va="center", fontsize=7.5)
        axes[0].set_yticks(y, [f"{i}\n(n={n:,.0f})" for i, n in zip(p.index, p["clips_captured"])], fontsize=8)
        axes[0].legend(fontsize=7.5, loc="upper right")
        axes[0].grid(axis="x")
        axes[0].xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
        dv.titled(axes[0], "14-day outcome by trigger class (post-launch)",
                  f"server record · launch week {o['launch_week']} excluded · compare classes, not to the daily tab")
    if t is not None:
        tt = t["table"].iloc[::-1]
        y = np.arange(len(tt))
        ax = axes[1]
        ax.barh(y + 0.2, tt["share_rate"], height=0.38, color=dv.BLACK, label="share rate")
        ax.barh(y - 0.2, tt["delete_rate"], height=0.38, color=dv.O_MID, label="delete rate")
        for yy, s, dd in zip(y, tt["share_rate"], tt["delete_rate"]):
            ax.text(s, yy + 0.2, f" {s:.1%}", va="center", fontsize=7.5)
            ax.text(dd, yy - 0.2, f" {dd:.0%}", va="center", fontsize=7.5)
        ax.set_yticks(y, [f"{n} [{v}]\n{pv:.0%} of volume" for n, v, pv in
                          zip(tt["trigger_name"], tt["verdict"], tt["pct_volume"])], fontsize=7.5)
        ax.axvline(t["avg_share"], color=dv.GRAY, ls=":", lw=1)
        ax.legend(fontsize=7.5, loc="upper right")
        ax.grid(axis="x")
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
        dv.titled(ax, "Which triggers are keepers vs junk",
                  "14-day share and delete rate per auto-clip trigger · dotted = average share rate")
    fig.tight_layout()
    return fig


def fig_return(A):
    rr = A["rr"]
    if rr is None:
        return None
    _style()
    t = rr["table"].set_index("got_autoclip")
    fig, ax = plt.subplots(figsize=(6.5, 3))
    y = np.arange(2)
    for k, (col, c) in enumerate([("wk2", dv.BLACK), ("wk5", dv.O_MID)]):
        vals = [t.loc[True, col], t.loc[False, col]]
        ax.barh(y + (0.2 if k == 0 else -0.2), vals, height=0.38, color=c, label=f"returned {col}")
        for yy, v in zip(y, vals):
            ax.text(v, yy + (0.2 if k == 0 else -0.2), f" {v:.0%}", va="center", fontsize=8)
    ax.set_yticks(y, [f"got auto-clip\n(n={t.loc[True, 'players']:,.0f})", f"no auto-clip\n(n={t.loc[False, 'players']:,.0f})"])
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="x")
    dv.titled(ax, "Return rate: correlation, not effect",
              "auto-clips go to players who played more that day — they'd return more anyway")
    return fig


def fig_external(A):
    x = A["ext"]
    if x is None:
        return None
    _style()
    e, L = x["e"], A["launch"]
    ms = [m for m in ("dau", "ccu_avg", "wishlists", "copies_sold") if m in x["res"]]
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.4))
    for ax in list(axes.flat)[len(ms):]:
        ax.axis("off")
    for ax, m in zip(axes.flat, ms):
        r = x["res"][m]
        ax.plot(e.index, e[m], color=dv.O_PALE, lw=0.8)
        ax.plot(e.index, e[m].rolling(7, min_periods=4).mean(), color=dv.BLACK, lw=1.4)
        if r["cf"] is not None:
            ax.plot(r["cf"].index, r["cf"].rolling(7).mean(), color=dv.GRAY, ls=":", lw=1.8)
        for a, b in spans(x["excl"]):
            ax.axvspan(a, b, color=dv.O_MID, alpha=0.18, lw=0)
        ax.axvline(L, color=dv.GRAY, ls="--", lw=1)
        _dates(ax, 2)
        ax.set_title({"dau": "DAU", "ccu_avg": "Avg concurrent", "wishlists": "Wishlist adds / day",
                      "copies_sold": "Copies sold / day"}[m], loc="left", fontsize=9.5, fontweight="bold", pad=15)
        net = x["res"].get(f"{m}_per_dau")
        stat = f"vs {'trend' if r['trend'] else 'baseline'} {_p(r['its'])} · {r['call']} · CI {_band(r)}"
        if net:
            stat += f"  |  per DAU {_p(net['its'])} · {net['call']}"
        ax.text(0, 1.015, stat, transform=ax.transAxes, fontsize=7.8, va="bottom",
                color=dv.O_DARK if r["call"] in ("UP", "DOWN") else "#666")
    fig.suptitle(f"{A['name']} (external): the studio's numbers around launch", x=0.01, ha="left", fontweight="bold")
    fig.text(0.01, 0.935, "pale = daily, black = 7-day rolling · orange shading = sale / DAU spikes (excluded from the fit) · "
             "dotted = projected baseline · dashed = auto-clip launch", fontsize=8, color="#666")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return fig


def platform(pl):
    if pl is None:
        return None
    p = pl.copy()
    p["auto_share"] = p["clips_autoclip"] / p["clips_total"]
    p["delete_ev_per_clip"] = p["delete_events"] / p["clips_total"]
    p["share_ev_per_clip"] = p["share_events"] / p["clips_total"]
    if "clippers_monthly_avg" in p and "players_monthly_avg" in p:
        p["clipper_rate"] = p["clippers_monthly_avg"] / p["players_monthly_avg"]
    p["rank"] = p["clips_total"].rank(ascending=False).astype(int)
    corr = p[["auto_share", "delete_ev_per_clip", "share_ev_per_clip"]].corr().loc["auto_share"]
    return dict(table=p.sort_values("clips_total", ascending=False).reset_index(drop=True), corr=corr)


def fig_platform(pv):
    _style()
    p = pv["table"]
    top = p.head(15).iloc[::-1]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw=dict(width_ratios=[1.2, 1]))
    ax = axes[0]
    y = np.arange(len(top))
    ax.barh(y, top["clips_total"] - top["clips_autoclip"], color=dv.BLACK, label="manual + other")
    ax.barh(y, top["clips_autoclip"], left=top["clips_total"] - top["clips_autoclip"], color=dv.O_MID, label="auto-clip")
    for yy, tot, a in zip(y, top["clips_total"], top["auto_share"]):
        ax.text(tot, yy, f" {tot / 1e6:,.1f}M · {a:.0%} auto", va="center", fontsize=7.5)
    ax.set_yticks(y, top["game"], fontsize=8)
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="x")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v / 1e6:,.0f}M"))
    dv.titled(ax, "Top games by clips captured", "Jan 1 – Sep 16 2026 · orange = captured by auto-clipping")
    ax = axes[1]
    focus = p["game"].str.lower().str.contains("rocket|ghost")
    for sub, col in ((p[~focus], dv.GRAY), (p[focus], dv.O_DARK)):
        ax.scatter(sub["auto_share"], sub["share_ev_per_clip"], s=30, color=col, zorder=3)
        ax.scatter(sub["auto_share"], sub["delete_ev_per_clip"], s=30, color=col, marker="x", zorder=3)
    for _, r in p[focus].iterrows():
        ax.annotate(r["game"], (r["auto_share"], r["delete_ev_per_clip"]), fontsize=8, xytext=(4, 2),
                    textcoords="offset points", color=dv.O_DARK)
    ax.set_xlabel("auto-clip share of clips")
    ax.set_ylabel("events per clip")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    dv.titled(ax, "More auto-clipping → more deletes, fewer shares per clip",
              "x = delete events / clip · dot = share events / clip · events, not distinct clips")
    fig.tight_layout()
    return fig
