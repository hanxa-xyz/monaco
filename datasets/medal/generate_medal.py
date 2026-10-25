"""Synthetic Medal dataset for the auto-clipping case (Rocket League + Ghost Janitors) and the
General Intuition "which clips are useful data" angle.

Row-level tables (players, sessions, clips) are generated first from a small set of PLANTED TRUTHS
(constants below); every aggregate — the packet-shaped daily / 14D / trigger / return-rate / platform
tables, the studio feeds, the weekly panel — is rolled up from those rows, so the dataset reconciles
with itself except where a wart is planted on purpose (and documented in README + answer_key.md).

    python3 generate_medal.py [--seed 7] [--out out]

Three identification strategies coexist so the analyst can compare them:
  1. a 10% randomized holdout per game (players.autoclip_holdout = 1 never get auto-clips)   — the clean A/B
  2. pre/post around the launches, with calendar confounds planted                           — what the packet gives
  3. four control games with no launch in the window                                           — difference-in-differences
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
START, END = pd.Timestamp("2026-02-01"), pd.Timestamp("2026-08-31")
AS_OF = pd.Timestamp("2026-09-01")                      # observation stops here; later outcomes are censored
DAYS = pd.date_range(START, END)
ND = len(DAYS)
RL_LAUNCH, GJ_LAUNCH = pd.Timestamp("2026-05-07"), pd.Timestamp("2026-05-21")
GJ_RELEASE = pd.Timestamp("2025-11-08")
HOLDOUT, RAMP_DAYS = 0.20, 10                           # randomized holdout share; client-update adoption ramp
CLIENT_OVER_SERVER = 4 / 3                              # daily (client) deletion count vs server rows
D = lambda n: pd.Timedelta(days=n)  # noqa: E731

# ---------------------------------------------------------------- planted truths (the answer key quotes these)
TRUTH = {
    "rl": dict(manual_change=-0.12,      # hotkey clips per session, auto-on vs holdout, post-launch
               activity_lift=0.02,       # daily play probability, auto-on vs holdout
               purge_window=("2026-06-15", "2026-06-18"), purge_share=0.6),
    "gj": dict(manual_change=0.00, activity_lift=0.05,
               penetration=0.07,         # Medal GJ players / studio DAU
               wishlists_per_share=1.5, copies_per_share=0.30,
               launch_discount=0.25, launch_discount_window=("2026-05-21", "2026-05-27"),
               content_patch="2026-06-04"),
    "val": dict(manual_change=-0.08, activity_lift=0.01),
}

# game_id, name, studio, model, store, launch, n_players, steam share, hotkey/session, native/unit, dur_mean, unit, units/min
GAMES = [
    dict(game_id=1, name="Rocket League", studio_id=1, model="f2p", store="epic", launch=RL_LAUNCH, n=2400,
         steam_share=0.08, manual_rate=1.10, auto_rate=0.45, dur_mean=55, unit="matches", unit_per_min=1 / 13, key="rl"),
    dict(game_id=2, name="Ghost Janitors", studio_id=2, model="paid", store="steam", launch=GJ_LAUNCH, n=1400,
         steam_share=1.0, manual_rate=0.70, auto_rate=0.30, dur_mean=70, unit="rounds", unit_per_min=1 / 30, key="gj"),
    dict(game_id=3, name="Valorant", studio_id=3, model="f2p", store="riot", launch=pd.Timestamp("2025-09-15"), n=600,
         steam_share=0.0, manual_rate=0.90, auto_rate=0.45, dur_mean=60, unit="matches", unit_per_min=1 / 28, key="val"),
    dict(game_id=4, name="Marvel Rivals", studio_id=4, model="f2p", store="steam", launch=None, n=500,
         steam_share=1.0, manual_rate=0.80, auto_rate=0.0, dur_mean=50, unit="matches", unit_per_min=1 / 12, key=None),
    dict(game_id=5, name="Phasmophobia", studio_id=5, model="paid", store="steam", launch=None, n=400,
         steam_share=1.0, manual_rate=0.60, auto_rate=0.0, dur_mean=65, unit="rounds", unit_per_min=1 / 25, key=None),
    dict(game_id=6, name="Lethal Company", studio_id=6, model="paid", store="steam", launch=None, n=350,
         steam_share=1.0, manual_rate=0.70, auto_rate=0.0, dur_mean=60, unit="rounds", unit_per_min=1 / 20, key=None),
]
STUDIOS = [
    dict(studio_id=1, studio_name="Psyonix", parent="Epic Games", country="US", tier="enterprise", integration_live=RL_LAUNCH, triggers_configured=7),
    dict(studio_id=2, studio_name="Interactive Wave Studio", parent=None, country="NL", tier="indie", integration_live=GJ_LAUNCH, triggers_configured=5),
    dict(studio_id=3, studio_name="Riot Games", parent="Tencent", country="US", tier="enterprise", integration_live=pd.Timestamp("2025-09-15"), triggers_configured=4),
    dict(studio_id=4, studio_name="NetEase Games", parent=None, country="CN", tier="enterprise", integration_live=None, triggers_configured=0),
    dict(studio_id=5, studio_name="Kinetic Games", parent=None, country="GB", tier="indie", integration_live=None, triggers_configured=0),
    dict(studio_id=6, studio_name="Zeekerss", parent=None, country="US", tier="indie", integration_live=None, triggers_configured=0),
]
# trigger_name, share of native volume, 14d delete rate, 14d share rate, public-post rate
TRIGGERS = {
    1: [("Goal", .30, .40, .025, .012), ("Save", .22, .55, .015, .006), ("Demolition", .18, .62, .008, .004),
        ("Assist", .12, .58, .010, .005), ("Win / MVP", .07, .35, .030, .015), ("Epic Save", .06, .22, .060, .030),
        ("Aerial Goal", .05, .18, .085, .045)],
    2: [("Brutal Jump Scare", .35, .15, .14, .07), ("Ghost Grab", .20, .25, .08, .04), ("Generator Blackout", .20, .50, .02, .01),
        ("Job Complete", .15, .55, .015, .008), ("Team Wipe", .10, .18, .12, .06)],
    3: [("Ace", .10, .20, .09, .05), ("Clutch", .15, .25, .07, .04), ("Multi-kill", .45, .50, .02, .01), ("Headshot", .30, .60, .012, .006)],
}
HOTKEY = dict(delete=.12, share=.095, post=.05)
STEAM = dict(delete=.22, share=.055, post=.03)
TIERS = dict(names=["light", "mid", "heavy"], share=[.50, .35, .15], p_day=[.02, .06, .18], clip_mult=[.6, 1.0, 1.6], share_mult=[.8, 1.0, 1.25],
             dur_mult=[.7, 1.0, 1.4])
COUNTRIES = (["US", "GB", "DE", "BR", "CA", "FR", "AU", "MX", "NL", "SE", None], [.54, .08, .07, .08, .05, .04, .03, .03, .02, .02, .04])

OTHER_GAMES = [  # platform-tab context: name, monthly players, native auto-clip?, on Steam?
    ("Roblox", 2_600_000, False, False), ("Fortnite", 2_100_000, True, False), ("Counter-Strike 2", 900_000, True, True),
    ("Grand Theft Auto V", 800_000, False, True), ("Minecraft", 700_000, False, False), ("Call of Duty", 550_000, False, True),
    ("Apex Legends", 500_000, True, True), ("League of Legends", 400_000, True, False), ("Rainbow Six Siege", 350_000, True, True),
    ("Overwatch 2", 300_000, True, True), ("Rust", 200_000, False, True), ("R.E.P.O.", 180_000, False, True),
    ("Dead by Daylight", 150_000, False, True),
]


# ---------------------------------------------------------------- calendar helpers
def weekend(days, size):
    return np.where(days.dayofweek >= 5, size, 0.0)


def summer(days, size=0.10):
    up = np.clip((days - pd.Timestamp("2026-06-12")).days.values / 18, 0, 1)
    down = np.clip((pd.Timestamp("2026-09-05") - days).days.values / 16, 0, 1)
    return size * up * down


def bump(days, start, size, half_life):
    t = (days - pd.Timestamp(start)).days.values.astype(float)
    return np.where(t >= 0, size * 0.5 ** (t / half_life), 0.0)


def window(days, a, b, size):
    return np.where((days >= pd.Timestamp(a)) & (days <= pd.Timestamp(b)), size, 0.0)


def gj_discounts(days):
    t = TRUTH["gj"]
    d = window(days, "2026-03-19", "2026-03-26", 0.30) + window(days, "2026-06-25", "2026-07-09", 0.45)
    a, b = t["launch_discount_window"]
    return d + window(days, a, b, t["launch_discount"])


def activity_multiplier(g, days):
    """Expected play-propensity multiplier per day for a game: weekday pattern, summer, seasons, sales, decay."""
    gid = g["game_id"]
    if gid == 1:
        return 1 + weekend(days, .18) + summer(days) + bump(days, "2026-06-10", .10, 7) + window(days, "2026-05-20", "2026-05-26", .06)
    if gid == 2:
        age = (days - GJ_RELEASE).days.values.astype(float)
        organic = 0.55 + 0.45 * np.exp(-(age - 85) / 60)
        return organic * (1 + weekend(days, .25) + .5 * summer(days) + bump(days, TRUTH["gj"]["content_patch"], .30, 8) + .6 * gj_discounts(days))
    if gid == 3:
        return 1 + weekend(days, .15) + summer(days) + bump(days, "2026-04-29", .08, 7) + bump(days, "2026-06-24", .08, 7)
    if gid == 4:
        return 1 + weekend(days, .20) + summer(days) + bump(days, "2026-07-10", .12, 10)
    if gid == 5:
        return 1 + weekend(days, .25) + .5 * summer(days) + window(days, "2026-06-25", "2026-07-09", .25)
    t = (days - START).days.values.astype(float)
    return (0.8 + 0.2 * np.exp(-t / 120)) * (1 + weekend(days, .25) + .5 * summer(days) + bump(days, "2026-07-15", .25, 8) + window(days, "2026-06-25", "2026-07-09", .35))


# ---------------------------------------------------------------- players
def make_players(rng):
    rows = []
    for g in GAMES:
        n = g["n"]
        tier = rng.choice(3, n, p=TIERS["share"])
        pre = rng.random(n) < 0.80
        signup = np.where(pre, START - pd.to_timedelta(rng.integers(30, 1200, n), unit="D"),
                          START + pd.to_timedelta(rng.integers(0, ND - 20, n), unit="D"))
        rows.append(pd.DataFrame({
            "player_id": np.zeros(n, dtype=int), "game_id": g["game_id"], "tier": tier,
            "signup_date": pd.to_datetime(signup).normalize(),
            "country": rng.choice(COUNTRIES[0], n, p=COUNTRIES[1]),
            "platform_os": rng.choice(["windows", "mac"], n, p=[.94, .06]),
            "premium": (rng.random(n) < 0.06).astype(int),
            "acq_channel": rng.choice(["organic", "friend_invite", "creator", "ad_quest"], n, p=[.55, .22, .13, .10]),
            "steam_linked": (rng.random(n) < g["steam_share"]).astype(int),
            "autoclip_holdout": (rng.random(n) < HOLDOUT).astype(int) if g["launch"] is not None else 0,
            "update_offset": rng.integers(0, RAMP_DAYS, n),                       # latent: days after launch until the client updated
            "hotkey_prop": rng.gamma(1.0, 1.0, n),                            # latent: heavy-tailed hotkey propensity
        }))
    P = pd.concat(rows, ignore_index=True)
    P["player_id"] = ["p%06d" % i for i in rng.choice(np.arange(100_000, 999_999), len(P), replace=False)]
    return P


# ---------------------------------------------------------------- sessions
HOUR_W = np.array([2, 1.5, 1, .6, .4, .3, .4, .6, 1, 1.5, 2, 2.5, 3, 3, 3.2, 3.5, 4, 5, 6, 7, 7.5, 7, 5.5, 3.5])


def make_sessions(P, rng):
    out = []
    for g in GAMES:
        pg = P[P.game_id == g["game_id"]]
        n = len(pg)
        mult = activity_multiplier(g, DAYS)
        p_day = np.array(TIERS["p_day"])[pg.tier.values]
        if g["launch"] is not None:
            on_day = (g["launch"] + pd.to_timedelta(pg.update_offset.values, unit="D")).values[:, None] <= DAYS.values[None, :]
            auto_on = on_day & (pg.autoclip_holdout.values[:, None] == 0)
            post = (DAYS.values[None, :] >= np.datetime64(g["launch"])) & np.ones((n, 1), bool)
            lift = 1 + TRUTH[g["key"]]["activity_lift"] * (pg.autoclip_holdout.values[:, None] == 0) * post
        else:
            auto_on = np.zeros((n, ND), bool)
            lift = np.ones((n, ND))
        prob = p_day[:, None] * mult[None, :] * lift
        prob = prob * (pg.signup_date.values[:, None] <= DAYS.values[None, :])
        hit = rng.random((n, ND)) < prob
        pi, di = np.nonzero(hit)
        k = len(pi)
        dur = np.clip(rng.lognormal(np.log(g["dur_mean"]) - 0.18, 0.6, k) * np.array(TIERS["dur_mult"])[pg.tier.values[pi]], 5, 300)
        units = rng.poisson(dur * g["unit_per_min"]) + 1
        hour = rng.choice(24, k, p=HOUR_W / HOUR_W.sum())
        start = DAYS[di] + pd.to_timedelta(hour * 3600 + rng.integers(0, 3600, k), unit="s")
        out.append(pd.DataFrame({
            "player_id": pg.player_id.values[pi], "game_id": g["game_id"], "session_date": DAYS[di],
            "start_ts": start, "duration_min": np.round(dur, 1), "units_played": units, "unit_type": g["unit"],
            "autoclip_on": auto_on[pi, di].astype(int), "won": (rng.random(k) < 0.5).astype(int),
            "tier": pg.tier.values[pi], "hotkey_prop": pg.hotkey_prop.values[pi], "steam_linked": pg.steam_linked.values[pi],
            "_gkey": g["key"] or "", "_dur_mean": g["dur_mean"], "_manual_rate": g["manual_rate"], "_auto_rate": g["auto_rate"],
            "_unit_mean": g["dur_mean"] * g["unit_per_min"] + 1,
        }))
    S = pd.concat(out, ignore_index=True).sort_values(["session_date", "start_ts"]).reset_index(drop=True)
    S["session_id"] = ["s%07d" % i for i in range(1, len(S) + 1)]
    return S


# ---------------------------------------------------------------- clips
def make_clips(S, rng):
    tier_clip = np.array(TIERS["clip_mult"])[S.tier.values]
    hype = np.where((S.game_id.values == 1) & (S.session_date.values >= np.datetime64("2026-05-20")) &
                    (S.session_date.values <= np.datetime64("2026-05-26")), 1.15, 1.0)
    manual_change = np.array([TRUTH[k]["manual_change"] if k else 0.0 for k in S._gkey.values])
    lam_hot = S._manual_rate.values * S.hotkey_prop.values * tier_clip * hype * (1 + manual_change * S.autoclip_on.values) \
        * np.sqrt(S.duration_min.values / S._dur_mean.values)
    lam_auto = S._auto_rate.values * S.units_played.values * S.autoclip_on.values
    steam_rate = np.select([S.game_id.values == 1, S.game_id.values == 2], [0.02, 0.07], 0.03)
    lam_steam = steam_rate * S.steam_linked.values * np.sqrt(S.duration_min.values / S._dur_mean.values)
    n_hot, n_auto, n_steam = rng.poisson(lam_hot), rng.poisson(lam_auto), rng.poisson(lam_steam)
    S["events_fired"] = n_auto + rng.binomial(n_auto, 0.03)                   # ~3% of trigger events fail to capture

    parts = []
    for cls, counts in (("hotkey", n_hot), ("autoclip_native", n_auto), ("autoclip_steam_achievement", n_steam)):
        idx = np.repeat(np.arange(len(S)), counts)
        parts.append(pd.DataFrame({"_s": idx, "trigger_class": cls}))
    C = pd.concat(parts, ignore_index=True)
    C = C.join(S[["session_id", "player_id", "game_id", "start_ts", "duration_min", "tier", "autoclip_on"]], on="_s")
    k = len(C)
    C["captured_ts"] = C.start_ts + pd.to_timedelta(rng.random(k) * C.duration_min.values * 60, unit="s")
    C["captured_ts"] = C.captured_ts.dt.floor("s")

    # trigger names + per-clip outcome probabilities
    C["trigger_name"] = None
    p_del = np.where(C.trigger_class == "hotkey", HOTKEY["delete"], STEAM["delete"]).astype(float)
    p_sh = np.where(C.trigger_class == "hotkey", HOTKEY["share"], STEAM["share"]).astype(float)
    p_post = np.where(C.trigger_class == "hotkey", HOTKEY["post"], STEAM["post"]).astype(float)
    for gid, trig in TRIGGERS.items():
        m = ((C.trigger_class == "autoclip_native") & (C.game_id == gid)).values
        if not m.any():
            continue
        w = np.array([t[1] for t in trig]); pick = rng.choice(len(trig), m.sum(), p=w / w.sum())
        C.loc[m, "trigger_name"] = np.array([t[0] for t in trig])[pick]
        p_del[m] = np.array([t[2] for t in trig])[pick]
        p_sh[m] = np.array([t[3] for t in trig])[pick]
        p_post[m] = np.array([t[4] for t in trig])[pick]
    C.loc[C.trigger_class == "autoclip_steam_achievement", "trigger_name"] = "Steam Achievement (rare)"
    share_mult = np.array(TIERS["share_mult"])[C.tier.values]
    p_sh = np.clip(p_sh * share_mult, 0, 0.95)
    p_del = np.clip(p_del * (2 - share_mult), 0, 0.97)       # heavy players curate less harshly
    C["_p_del"], C["_p_sh"] = p_del, p_sh

    # media attributes (the General Intuition angle: is this clip useful training data?)
    is_auto = (C.trigger_class != "hotkey").values
    C["duration_s"] = np.where(is_auto, rng.choice([20, 25, 30], k, p=[.3, .3, .4]), rng.choice([15, 30, 60], k, p=[.15, .70, .15]))
    C["resolution"] = rng.choice(["1080p", "1440p", "720p"], k, p=[.68, .20, .12])
    C["fps"] = rng.choice([60, 30, 120], k, p=[.75, .18, .07])
    C["input_log_attached"] = (rng.random(k) < np.where(is_auto, 0.85, 0.60)).astype(int)
    C["motion_score"] = np.round(np.clip(rng.beta(np.where(is_auto, 3.0, 2.0), 2.0, k), 0, 1), 3)
    bitrate = np.select([C.resolution == "720p", C.resolution == "1440p"], [0.30, 0.95], 0.60) * np.where(C.fps == 120, 1.4, 1.0)
    C["storage_mb"] = np.round(C.duration_s.values * bitrate * rng.lognormal(0, 0.08, k), 1)

    # outcomes: deletion, off-platform share, public post (server record at capture)
    deleted = rng.random(k) < p_del
    within14 = rng.random(k) < 0.85
    lag = np.where(within14, np.minimum(rng.geometric(0.25, k) - 1, 13), 14 + np.minimum(rng.geometric(0.03, k), 110))
    del_ts = C.captured_ts + pd.to_timedelta(lag, unit="D") + pd.to_timedelta(rng.integers(60, 20 * 3600, k), unit="s")
    C["deleted_ts"] = del_ts.where(deleted & (del_ts < AS_OF))
    shared = rng.random(k) < p_sh
    sh_lag = np.where(rng.random(k) < 0.75, 0, rng.integers(1, 14, k))
    sh_ts = C.captured_ts + pd.to_timedelta(sh_lag, unit="D") + pd.to_timedelta(rng.integers(30, 6 * 3600, k), unit="s")
    sh_ts = sh_ts.where(~(deleted & (sh_ts > del_ts)), C.captured_ts + pd.to_timedelta(rng.integers(30, 600, k), unit="s"))
    C["shared_ts"] = sh_ts.where(shared & (sh_ts < AS_OF))
    C["posted_public"] = (rng.random(k) < p_post).astype(int)

    # planted: a Medal client "free up space" prompt → bulk purge of OLD Rocket League clips, any age
    a, b = (pd.Timestamp(x) for x in TRUTH["rl"]["purge_window"])
    old = (C.game_id == 1) & (C.captured_ts < pd.Timestamp("2026-04-15")) & C.deleted_ts.isna()
    purgers = rng.choice(C.loc[old, "player_id"].unique(), int(0.35 * C.loc[old, "player_id"].nunique()), replace=False)
    purge = old & C.player_id.isin(purgers) & (rng.random(k) < TRUTH["rl"]["purge_share"])
    C.loc[purge, "deleted_ts"] = a + pd.to_timedelta(rng.integers(0, (b - a).days + 1, purge.sum()), unit="D") \
        + pd.to_timedelta(rng.integers(8 * 3600, 23 * 3600, purge.sum()), unit="s")
    C["_purged"] = purge

    # 14-day outcome flags, censored when the clip is too young
    age_ok = C.captured_ts + D(14) <= AS_OF
    C["deleted_14d"] = np.where(age_ok, ((C.deleted_ts - C.captured_ts) <= D(14)).fillna(False).astype(int), np.nan)
    C["shared_14d"] = np.where(age_ok, ((C.shared_ts - C.captured_ts) <= D(14)).fillna(False).astype(int), np.nan)
    C = C.sort_values("captured_ts").reset_index(drop=True)
    C["clip_id"] = ["c%08d" % i for i in range(1, len(C) + 1)]
    C["captured_date"] = C.captured_ts.dt.normalize()
    return C


# ---------------------------------------------------------------- aggregates (packet-shaped)
DAILY_COLS = ["players", "clips_total", "clips_autoclip_native", "clips_autoclip_steam_achievement", "clippers_total",
              "clippers_autoclip", "clips_deleted_distinct", "users_deleting", "clips_shared_distinct", "users_sharing",
              "public_posts_total", "public_posts_autoclip_native", "users_posting"]


def game_daily(S, C):
    grid = pd.MultiIndex.from_product([[g["game_id"] for g in GAMES], DAYS], names=["game_id", "date"])
    s = S.groupby(["game_id", "session_date"]).player_id.nunique().rename("players")
    s.index.names = ["game_id", "date"]
    c = C.groupby(["game_id", "captured_date"])
    agg = pd.DataFrame({
        "clips_total": c.size(),
        "clips_autoclip_native": c.trigger_class.apply(lambda x: (x == "autoclip_native").sum()),
        "clips_autoclip_steam_achievement": c.trigger_class.apply(lambda x: (x == "autoclip_steam_achievement").sum()),
        "clippers_total": c.player_id.nunique(),
        "clippers_autoclip": C[C.trigger_class != "hotkey"].groupby(["game_id", "captured_date"]).player_id.nunique(),
        "public_posts_total": c.posted_public.sum(),
        "public_posts_autoclip_native": C[C.trigger_class == "autoclip_native"].groupby(["game_id", "captured_date"]).posted_public.sum(),
        "users_posting": C[C.posted_public == 1].groupby(["game_id", "captured_date"]).player_id.nunique(),
    })
    agg.index.names = ["game_id", "date"]
    dl = C.dropna(subset=["deleted_ts"]).assign(d=lambda x: x.deleted_ts.dt.normalize()).groupby(["game_id", "d"])
    sh = C.dropna(subset=["shared_ts"]).assign(d=lambda x: x.shared_ts.dt.normalize()).groupby(["game_id", "d"])
    extra = pd.DataFrame({"clips_deleted_distinct": np.round(dl.size() * CLIENT_OVER_SERVER), "users_deleting": dl.player_id.nunique(),
                          "clips_shared_distinct": sh.size(), "users_sharing": sh.player_id.nunique()})
    extra.index.names = ["game_id", "date"]
    out = pd.concat([s, agg, extra], axis=1).reindex(grid).fillna(0).astype(int).reset_index()
    out["players"] = np.maximum(out.players, out.clippers_total)
    return out[["game_id", "date"] + DAILY_COLS]


def outcomes_14d(C):
    c = C[C.deleted_14d.notna()].copy()
    c["week"] = c.captured_date - pd.to_timedelta(c.captured_date.dt.dayofweek, unit="D")
    o = c.groupby(["game_id", "week", "trigger_class"]).agg(clips_captured=("clip_id", "size"), deleted_within_14d=("deleted_14d", "sum"),
                                                              shared_within_14d=("shared_14d", "sum"), public_posts=("posted_public", "sum")).reset_index()
    for k in ("deleted_within_14d", "shared_within_14d", "public_posts"):
        o[k] = o[k].astype(int)
    return o[o.week >= pd.Timestamp("2026-02-02")]


def trigger_breakdown(C):
    rows = []
    for g in GAMES:
        if g["launch"] is None:
            continue
        c = C[(C.game_id == g["game_id"]) & (C.trigger_class != "hotkey") & (C.captured_date >= g["launch"]) & C.deleted_14d.notna()]
        t = c.groupby("trigger_name").agg(clips_captured=("clip_id", "size"), deleted_within_14d=("deleted_14d", "sum"),
                                          shared_within_14d=("shared_14d", "sum"), public_posts=("posted_public", "sum")).reset_index()
        t.insert(0, "game_id", g["game_id"])
        rows.append(t)
    out = pd.concat(rows, ignore_index=True)
    for k in ("deleted_within_14d", "shared_within_14d", "public_posts"):
        out[k] = out[k].astype(int)
    return out.sort_values(["game_id", "clips_captured"], ascending=[True, False]).reset_index(drop=True)


def return_rate(S, C):
    """Packet grain: player-days from launch+10 to END-36, split by whether the player got a native auto-clip that day."""
    native_days = C[C.trigger_class == "autoclip_native"].groupby(["game_id", "player_id", "captured_date"]).size().index
    native = pd.Series(True, index=native_days, name="got_autoclip")
    rows, detail = [], []
    for g in GAMES:
        if g["launch"] is None or g["key"] == "val":
            continue
        s = S[(S.game_id == g["game_id"])][["player_id", "session_date"]].drop_duplicates()
        s = s.rename(columns={"session_date": "d"})
        s["got_autoclip"] = s.set_index([pd.Index([g["game_id"]] * len(s)), s.player_id, s.d]).index.isin(native.index)
        played = set(zip(s.player_id, s.d))
        m = (s.d >= g["launch"] + D(10)) & (s.d <= END - D(36))
        w = s[m].copy()
        w["returned_wk2"] = [any((p, d + D(k)) in played for k in range(7, 14)) for p, d in zip(w.player_id, w.d)]
        w["returned_wk5"] = [any((p, d + D(k)) in played for k in range(30, 37)) for p, d in zip(w.player_id, w.d)]
        w.insert(0, "game_id", g["game_id"])
        detail.append(w.rename(columns={"d": "session_date"}))
        r = w.groupby("got_autoclip").agg(players=("player_id", "size"), returned_wk2=("returned_wk2", "sum"), returned_wk5=("returned_wk5", "sum")).reset_index()
        r.insert(0, "game_id", g["game_id"])
        rows.append(r)
    return pd.concat(rows, ignore_index=True), pd.concat(detail, ignore_index=True)


def launch_cohort(P, S, C):
    """A/B table: players active in the 28 days before launch, holdout vs auto-on, pre covariates and 14/28-day outcomes."""
    rows = []
    for g in GAMES:
        if g["launch"] is None or g["key"] == "val":
            continue
        L = g["launch"]
        s = S[S.game_id == g["game_id"]]
        c = C[C.game_id == g["game_id"]]
        pre = s[(s.session_date >= L - D(28)) & (s.session_date < L)]
        cohort = pre.player_id.unique()
        base = P[P.player_id.isin(cohort)][["player_id", "game_id", "autoclip_holdout", "premium", "steam_linked", "acq_channel", "country", "signup_date"]].copy()
        base["tenure_days_at_launch"] = (L - base.signup_date).dt.days
        base = base.drop(columns="signup_date")
        pre_c = c[(c.captured_date >= L - D(28)) & (c.captured_date < L)]
        base["pre28_sessions"] = base.player_id.map(pre.groupby("player_id").size()).fillna(0).astype(int)
        base["pre28_minutes"] = base.player_id.map(pre.groupby("player_id").duration_min.sum()).fillna(0).round(0)
        base["pre28_manual_clips"] = base.player_id.map(pre_c.groupby("player_id").size()).fillna(0).astype(int)
        base["pre28_shares"] = base.player_id.map(pre_c.dropna(subset=["shared_ts"]).groupby("player_id").size()).fillna(0).astype(int)
        post = s[(s.session_date >= L) & (s.session_date < L + D(14))]
        post_c = c[(c.captured_date >= L) & (c.captured_date < L + D(14))]
        base["post14_sessions"] = base.player_id.map(post.groupby("player_id").size()).fillna(0).astype(int)
        base["post14_clips_total"] = base.player_id.map(post_c.groupby("player_id").size()).fillna(0).astype(int)
        base["post14_manual_clips"] = base.player_id.map(post_c[post_c.trigger_class == "hotkey"].groupby("player_id").size()).fillna(0).astype(int)
        base["post14_auto_clips"] = base.player_id.map(post_c[post_c.trigger_class != "hotkey"].groupby("player_id").size()).fillna(0).astype(int)
        base["got_autoclip_14d"] = (base.post14_auto_clips > 0).astype(int)
        base["post14_shares"] = base.player_id.map(post_c.dropna(subset=["shared_ts"]).groupby("player_id").size()).fillna(0).astype(int)
        base["post14_deletes"] = base.player_id.map(post_c.dropna(subset=["deleted_ts"]).groupby("player_id").size()).fillna(0).astype(int)
        first_auto = c[c.trigger_class == "autoclip_native"].groupby("player_id").captured_date.min()
        base["first_autoclip_date"] = base.player_id.map(first_auto)
        for lo, hi in ((14, 28), (28, 42)):
            w = s[(s.session_date >= L + D(lo)) & (s.session_date < L + D(hi))].player_id.unique()
            base[f"retained_d{lo}_{hi - 1}"] = base.player_id.isin(w).astype(int)
        rows.append(base)
    return pd.concat(rows, ignore_index=True)


def studio_daily(S, C, rng):
    """External (studio-side) feeds for the two paid partners with data-sharing: GJ (treated) and Lethal Company (control)."""
    out = []
    for g in GAMES:
        if g["game_id"] not in (2, 6):
            continue
        medal = S[S.game_id == g["game_id"]].groupby("session_date").player_id.nunique().reindex(DAYS).fillna(0).values
        mult = activity_multiplier(g, DAYS)
        if g["game_id"] == 2:
            t = TRUTH["gj"]
            expected_medal = medal.mean() * mult / mult.mean()
            base_dau = expected_medal / t["penetration"] * rng.lognormal(0, 0.04, ND)
            disc, patch = gj_discounts(DAYS), bump(DAYS, t["content_patch"], .30, 8)
            age = (DAYS - GJ_RELEASE).days.values.astype(float)
            decay = 0.45 + 0.55 * np.exp(-(age - 85) / 50)
            wish_base = 110 * decay * (1 + weekend(DAYS, .15) + 1.5 * patch + 2.0 * disc)
            copies_base = 45 * decay * (1 + weekend(DAYS, .20) + patch + 8.0 * disc)
            auto_shares = C[(C.game_id == 2) & (C.trigger_class == "autoclip_native")].dropna(subset=["shared_ts"]) \
                .assign(d=lambda x: x.shared_ts.dt.normalize()).groupby("d").size().reindex(DAYS).fillna(0).values
            lagk = np.array([0, .5, .3, .2])
            incr_w = np.convolve(auto_shares, lagk)[:ND] * t["wishlists_per_share"]
            incr_c = np.convolve(auto_shares, lagk)[:ND] * t["copies_per_share"]
            dau = base_dau + np.convolve(incr_c, np.full(14, 0.3))[:ND]
            wish = rng.poisson((wish_base + incr_w) * rng.lognormal(0, 0.10, ND))
            copies = rng.poisson((copies_base + incr_c) * rng.lognormal(0, 0.10, ND))
            TRUTH["gj"]["_incr_wish"], TRUTH["gj"]["_incr_copies"] = incr_w, incr_c
            TRUTH["gj"]["_wish"], TRUTH["gj"]["_copies"], TRUTH["gj"]["_dau"], TRUTH["gj"]["_medal"] = wish, copies, dau, medal
        else:
            dau = 6_000 * mult / mult[0] * rng.lognormal(0, 0.04, ND)
            disc = window(DAYS, "2026-06-25", "2026-07-09", .35)
            patch = bump(DAYS, "2026-07-15", .25, 8)
            wish = rng.poisson(140 * (1 + weekend(DAYS, .15) + 1.5 * patch + 2.0 * disc) * rng.lognormal(0, 0.10, ND))
            copies = rng.poisson(70 * (1 + weekend(DAYS, .20) + patch + 8.0 * disc) * rng.lognormal(0, 0.10, ND))
        e = pd.DataFrame({"game_id": g["game_id"], "date": DAYS, "dau": np.round(dau).astype(int),
                          "ccu_peak": np.round(dau * rng.uniform(.11, .13, ND)).astype(int),
                          "ccu_avg": np.round(dau * rng.uniform(.055, .065, ND)).astype(int),
                          "copies_sold": copies, "wishlists": wish})
        e["copies_sold_change"] = e.copies_sold.diff().fillna(0).astype(int)
        e["wishlists_change"] = e.wishlists.diff().fillna(0).astype(int)
        out.append(e)
    return pd.concat(out, ignore_index=True)


def studio_monthly(P, S, C, rng):
    s = S.assign(month=S.session_date.dt.to_period("M").dt.to_timestamp())
    c = C.assign(month=C.captured_date.dt.to_period("M").dt.to_timestamp())
    gs = {g["game_id"]: g for g in GAMES}
    rows = []
    for st in STUDIOS:
        gid = next(g["game_id"] for g in GAMES if g["studio_id"] == st["studio_id"])
        for m in pd.period_range(START, END, freq="M").to_timestamp():
            sm, cm = s[(s.game_id == gid) & (s.month == m)], c[(c.game_id == gid) & (c.month == m)]
            auto = cm[cm.trigger_class != "hotkey"]
            live = st["integration_live"] is not None and st["integration_live"] <= m + pd.offsets.MonthEnd(0)
            launch_month = st["integration_live"] is not None and st["integration_live"].to_period("M").to_timestamp() == m
            rows.append(dict(
                studio_id=st["studio_id"], game_id=gid, month=m.date(), integration_live=int(live),
                sdk_version=("2.3.1" if m >= pd.Timestamp("2026-06-01") else "2.2.0") if live else None,
                triggers_configured=st["triggers_configured"] if live else 0,
                medal_players=sm.player_id.nunique(), medal_player_days=len(sm), medal_minutes=int(sm.duration_min.sum()),
                clips_total=len(cm), autoclips=len(auto), autoclip_shares=int(auto.shared_ts.notna().sum()),
                shares_total=int(cm.shared_ts.notna().sum()), public_posts=int(cm.posted_public.sum()),
                est_offplatform_views=int(cm.shared_ts.notna().sum() * rng.uniform(35, 55)),
                api_errors=int(rng.poisson(40 if launch_month else (4 if live else 0))),
                support_tickets=int(rng.poisson(6 if launch_month else (1 if live else 0.3))),
                business_model=gs[gid]["model"], partner_tier=st["tier"],
            ))
    return pd.DataFrame(rows)


def platform_table(GD, rng):
    rows = []
    months = (END - START).days / 30.4
    for name, mau, native, steam in OTHER_GAMES:
        mau = mau * rng.lognormal(0, 0.05)
        manual = mau * rng.uniform(6, 12) * months
        auto = mau * months * ((rng.uniform(8, 25) if native else 0) + (rng.uniform(0.1, 0.3) if steam else 0))
        rows.append(dict(game=name, players_monthly_avg=mau, clippers_monthly_avg=mau * (0.33 + (0.35 if native else 0)) * rng.uniform(.9, 1.1),
                         clips_total=manual + auto, clips_autoclip=auto, delete_events=(manual * .13 + auto * .42) * rng.uniform(1.0, 1.1),
                         share_events=(manual * .10 + auto * .025) * rng.uniform(1.25, 1.45), public_posts=manual * .05 + auto * .01))
    # our six games, scaled up to platform size (the row-level sample is a ~1/40 slice of each game's Medal population)
    SCALE = 40
    for g in GAMES:
        d = GD[GD.game_id == g["game_id"]]
        mau_ratio = 0.22 if g["model"] == "f2p" else 0.18
        rows.append(dict(game=g["name"], players_monthly_avg=d.players.mean() * SCALE / mau_ratio,
                         clippers_monthly_avg=d.clippers_total.mean() * SCALE / (mau_ratio * 1.1), clips_total=d.clips_total.sum() * SCALE,
                         clips_autoclip=(d.clips_autoclip_native.sum() + d.clips_autoclip_steam_achievement.sum()) * SCALE,
                         delete_events=d.clips_deleted_distinct.sum() * SCALE * 1.05, share_events=d.clips_shared_distinct.sum() * SCALE * 1.35,
                         public_posts=d.public_posts_total.sum() * SCALE))
    df = pd.DataFrame(rows)
    num = df.columns[1:]
    df[num] = df[num].round().astype(int)
    return df.sort_values("clips_total", ascending=False).reset_index(drop=True)


def weekly_panel(GD):
    d = GD.assign(week=GD.date - pd.to_timedelta(GD.date.dt.dayofweek, unit="D"))
    d["clips_manual"] = d.clips_total - d.clips_autoclip_native - d.clips_autoclip_steam_achievement
    w = d.groupby(["game_id", "week"]).agg(player_days=("players", "sum"), clips_total=("clips_total", "sum"), clips_manual=("clips_manual", "sum"),
                                           clips_auto=("clips_autoclip_native", "sum"), shares=("clips_shared_distinct", "sum"),
                                           deletes_client=("clips_deleted_distinct", "sum"), public_posts=("public_posts_total", "sum")).reset_index()
    launch = {g["game_id"]: g["launch"] for g in GAMES}
    w["treated"] = w.game_id.isin([1, 2]).astype(int)
    w["post"] = [int(launch[g] is not None and wk >= launch[g] - D(launch[g].dayofweek)) for g, wk in zip(w.game_id, w.week)]
    w["manual_per_player_day"] = (w.clips_manual / w.player_days).round(4)
    w["shares_per_player_day"] = (w.shares / w.player_days).round(4)
    w["share_per_clip"] = (w.shares / w.clips_total.replace(0, np.nan)).round(4)
    return w[w.week >= pd.Timestamp("2026-02-02")]


# ---------------------------------------------------------------- warts (planted on the written copies only)
def wart_players(P, rng):
    out = P.drop(columns=["tier", "update_offset", "hotkey_prop"]).copy()
    deleted = rng.choice(out.player_id, 15, replace=False)            # deleted accounts → orphan sessions/clips
    out = out[~out.player_id.isin(deleted)]
    return out.rename(columns={"game_id": "primary_game_id"}), list(deleted)


def wart_sessions(S):
    cols = ["session_id", "player_id", "game_id", "session_date", "start_ts", "duration_min", "units_played", "unit_type",
            "autoclip_on", "events_fired", "won"]
    return S[cols].copy()


def wart_clips(C, rng):
    cols = ["clip_id", "session_id", "player_id", "game_id", "captured_ts", "trigger_class", "trigger_name", "duration_s", "resolution", "fps",
            "input_log_attached", "motion_score", "storage_mb", "deleted_ts", "shared_ts", "posted_public", "deleted_14d", "shared_14d"]
    out = C[cols].copy()
    k = len(out)
    native = (out.trigger_class == "autoclip_native").values
    m_null = native & (rng.random(k) < 0.02)                          # trigger name lost on 2% of native clips
    out.loc[m_null, "trigger_name"] = None
    m_case = native & ~m_null & (rng.random(k) < 0.03)                # casing drift from an older client build
    out.loc[m_case, "trigger_name"] = out.loc[m_case, "trigger_name"].str.lower()
    m_dur = rng.random(k) < 0.01                                      # missing duration
    out.loc[m_dur, "duration_s"] = np.nan
    skew = rng.choice(np.nonzero(out.deleted_ts.notna().values)[0], 30, replace=False)   # clock skew: deleted before captured
    out.iloc[skew, out.columns.get_loc("deleted_ts")] = out.iloc[skew]["captured_ts"] - pd.to_timedelta(rng.integers(60, 3600, 30), unit="s")
    dupes = out.sample(frac=0.012, random_state=int(rng.integers(0, 2**31)))              # double-logged capture events
    out = pd.concat([out, dupes]).sort_values(["captured_ts", "clip_id"]).reset_index(drop=True)
    return out, dict(trigger_name_null=int(m_null.sum()), trigger_name_lowercased=int(m_case.sum()), duration_null=int(m_dur.sum()),
                     clock_skew_rows=len(skew), duplicate_rows=len(dupes))


def wart_game_daily(GD):
    out = GD.copy()
    return out[~((out.game_id == 1) & (out.date == pd.Timestamp("2026-07-04")))]       # one missing RL day (pipeline outage)


def wart_studio_daily(E):
    dup = E[(E.game_id == 2) & (E.date == pd.Timestamp("2026-06-30"))]
    return pd.concat([E, dup]).sort_values(["game_id", "date"]).reset_index(drop=True)      # one duplicated GJ day


# ---------------------------------------------------------------- answer key
def pct(x):
    return "n/a" if x is None or pd.isna(x) else f"{x:+.1%}"


def answer_key(P, S, C, RRD, LC, GD, E, warts, deleted_players):
    L = []
    for g in GAMES:
        if g["key"] not in ("rl", "gj"):
            continue
        t, gid, launch = TRUTH[g["key"]], g["game_id"], g["launch"]
        s = S[(S.game_id == gid)].merge(P[["player_id", "autoclip_holdout", "tier"]], on="player_id")
        c = C[C.game_id == gid]
        post = s[(s.session_date >= launch + D(14))]                 # full post period after the 2-week client ramp
        pre = s[(s.session_date < launch)]                            # full pre period
        hot = c[c.trigger_class == "hotkey"].groupby("session_id").size()

        def per_session(sub):
            return sub.session_id.map(hot).fillna(0).mean()
        on, ho = post[post.autoclip_holdout == 0], post[post.autoclip_holdout == 1]
        pre_on, pre_ho = pre[pre.autoclip_holdout == 0], pre[pre.autoclip_holdout == 1]
        man_ab = per_session(on) / per_session(ho) - 1
        man_pre = per_session(pre_on) / per_session(pre_ho) - 1
        man_naive = per_session(post) / per_session(pre) - 1
        man_did = (per_session(on) / per_session(pre_on)) / (per_session(ho) / per_session(pre_ho)) - 1
        # activity: sessions per cohort player, post window, on vs holdout
        coh = LC[LC.game_id == gid]
        act = coh.groupby("autoclip_holdout").post14_sessions.mean()
        post_pp = post.merge(coh[["player_id", "autoclip_holdout"]], on="player_id", suffixes=("", "_c")).groupby("autoclip_holdout_c").size() \
            / coh.groupby("autoclip_holdout").size()
        pre_pp = pre.merge(coh[["player_id", "autoclip_holdout"]], on="player_id", suffixes=("", "_c")).groupby("autoclip_holdout_c").size() \
            / coh.groupby("autoclip_holdout").size()
        act_did = (post_pp[0] / pre_pp[0]) / (post_pp[1] / pre_pp[1]) - 1
        ret = coh.groupby("autoclip_holdout").retained_d14_27.mean()
        ret2 = coh.groupby("autoclip_holdout").retained_d28_41.mean()
        naive_ret = coh.groupby("got_autoclip_14d").retained_d14_27.mean()
        n_on, n_ho = (coh.autoclip_holdout == 0).sum(), (coh.autoclip_holdout == 1).sum()
        se_ret = np.sqrt(ret.get(0, .5) * (1 - ret.get(0, .5)) / n_on + ret.get(1, .5) * (1 - ret.get(1, .5)) / n_ho)
        rr = RRD[RRD.game_id == gid].groupby("got_autoclip").returned_wk2.mean()
        d = GD[GD.game_id == gid].set_index("date")
        spc_pre = (d.clips_shared_distinct / d.clips_total)[launch - D(28):launch - D(1)].mean()
        spc_post = (d.clips_shared_distinct / d.clips_total)[launch + D(14):launch + D(41)].mean()
        spp_pre = (d.clips_shared_distinct / d.players)[launch - D(28):launch - D(1)].mean()
        spp_post = (d.clips_shared_distinct / d.players)[launch + D(14):launch + D(41)].mean()
        o = c[c.deleted_14d.notna() & (c.captured_date >= launch)].groupby("trigger_class")[["deleted_14d", "shared_14d"]].mean()
        tr = c[c.deleted_14d.notna() & (c.captured_date >= launch) & (c.trigger_class == "autoclip_native")] \
            .groupby("trigger_name")[["deleted_14d", "shared_14d"]].mean().sort_values("shared_14d", ascending=False)
        L += [f"## {g['name']} (launch {launch.date()}; holdout {HOLDOUT:.0%} of players never get auto-clips)", "",
              f"- PLANTED manual-clip change (auto-on vs holdout): **{pct(t['manual_change'])}**. Realized hotkey clips per session, post = d14…Aug 31, pre = Feb 1…launch: "
              f"raw A/B {pct(man_ab)} · same contrast pre-launch (placebo) {pct(man_pre)} · **DiD (post/pre, on vs holdout) {pct(man_did)}** · "
              f"naive pre/post all players {pct(man_naive)}. Hotkey propensity is heavy-tailed, so the raw A/B carries the pre-period imbalance; the DiD is the check (SE ≈ 4–5%).",
              f"- PLANTED daily-activity lift for auto-on players: **{pct(t['activity_lift'])}**. Realized sessions per cohort player, first 14 days: "
              f"auto-on {act.get(0, np.nan):.2f} vs holdout {act.get(1, np.nan):.2f} ({pct(act.get(0, np.nan) / act.get(1, np.nan) - 1)}); "
              f"full post period, sessions per cohort player: on {post_pp[0]:.1f} vs holdout {post_pp[1]:.1f} ({pct(post_pp[0] / post_pp[1] - 1)}), "
              f"**DiD vs each group's own pre-period {pct(act_did)}**",
              f"- Retention d14–27 (any session), cohort = active in 28 pre-launch days: auto-on {ret.get(0, np.nan):.1%} vs holdout {ret.get(1, np.nan):.1%} "
              f"→ realized ATE **{(ret.get(0, np.nan) - ret.get(1, np.nan)) * 100:+.1f} pp** (SE {se_ret * 100:.1f} pp, n={n_on}/{n_ho}); "
              f"d28–41: {(ret2.get(0, np.nan) - ret2.get(1, np.nan)) * 100:+.1f} pp. The planted mechanism is a {pct(t['activity_lift'])} daily-activity lift, so the expected ATE is ~1–3 pp: an estimate inside the SE band passes.",
              f"- SELECTION TRAP: naive 'got an auto-clip in first 14d' vs not → {(naive_ret.get(1, np.nan) - naive_ret.get(0, np.nan)) * 100:+.1f} pp; "
              f"packet Return-rate table wk2 gap {(rr.get(True, np.nan) - rr.get(False, np.nan)) * 100:+.1f} pp — engagement tier drives both",
              f"- DILUTION: shares per clip {spc_pre:.2%} → {spc_post:.2%}; shares per player-day {spp_pre:.3f} → {spp_post:.3f} ({pct(spp_post / spp_pre - 1)})",
              "- 14-day outcomes post-launch, realized (server rows): " + "; ".join(f"{k}: deleted {v.deleted_14d:.0%}, shared {v.shared_14d:.1%}" for k, v in o.iterrows()),
              "- Triggers (share / delete): " + "; ".join(f"{k} {v.shared_14d:.1%}/{v.deleted_14d:.0%}" for k, v in tr.iterrows()),
              ]
        if g["key"] == "rl":
            a, b = t["purge_window"]
            L.append(f"- PLANTED bulk purge of OLD clips {a}…{b}: {int(c._purged.sum()):,} clips captured before Apr 15 deleted in that window "
                     f"(any-age, client prompt — not auto-clip junk). Daily `clips_deleted_distinct` is client-side = server rows × {CLIENT_OVER_SERVER:.2f}.")
            L.append("- Calendar: RLCS Paris Major May 20–26 (+6% players, +15% hotkey clips), in-game season Jun 10 (+10% decaying), summer from mid-June, weekends +18%.")
            L.append("- Junk triggers: Demolition, Assist, Save. Keepers: Aerial Goal, Epic Save. Goal is volume, middling quality.")
        else:
            e = E[E.game_id == 2].set_index("date")
            post_m = DAYS >= launch
            iw, ic = t["_incr_wish"][post_m].sum(), t["_incr_copies"][post_m].sum()
            pen = (t["_medal"] / t["_dau"]).mean()
            L += [f"- PLANTED Medal penetration of studio DAU: **{t['penetration']:.0%}** (realized {pen:.1%}) — caps any direct effect.",
                  f"- PLANTED wishlists per auto-clip share **{t['wishlists_per_share']}**, copies per share **{t['copies_per_share']}** (lag 0–3 days).",
                  f"- Realized incremental, {launch.date()}…{END.date()}: wishlists **{iw:,.0f}** of {e.wishlists[launch:].sum():,} "
                  f"({iw / e.wishlists[launch:].sum():.1%}); copies **{ic:,.0f}** of {e.copies_sold[launch:].sum():,} ({ic / e.copies_sold[launch:].sum():.1%}). "
                  "Small by design: the honest read is 'underpowered', not 'no effect'.",
                  f"- CONFOUNDS: launch-week {t['launch_discount']:.0%} discount {t['launch_discount_window'][0]}…{t['launch_discount_window'][1]} "
                  f"(copies ×~3, DAU +25%); content patch {t['content_patch']} (+30% DAU decaying); Steam Spring Sale Mar 19–26 and Summer Sale Jun 25–Jul 9; "
                  "post-release decay since Nov 8 2025. Lethal Company (game_id 6) is the untreated paid control with the same Summer Sale and its own patch Jul 15.",
                  "- Keepers: Brutal Jump Scare, Team Wipe. Junk: Generator Blackout, Job Complete.",
                  ]
        L.append("")
    L += ["## Controls and the panel", "",
          "- Valorant (game_id 3): auto-clip live since 2025-09-15 → always-treated in the window (with its own 10% holdout). "
          f"PLANTED manual change {pct(TRUTH['val']['manual_change'])}, activity lift {pct(TRUTH['val']['activity_lift'])}.",
          "- Marvel Rivals, Phasmophobia, Lethal Company (4–6): never treated. Each has its own calendar (patch bumps, Summer Sale).",
          "- `game_weekly_panel.csv` (game × week, treated/post flags) is the DiD input; parallel trends hold by construction except for each game's own calendar events.",
          "", "## Data-quality warts (exact counts)", "",
          f"- players.csv: {len(deleted_players)} accounts deleted → their sessions/clips are orphans (player_id not in players.csv): {deleted_players}",
          f"- clips.csv: {warts['duplicate_rows']:,} exact duplicate rows (double-logged captures); {warts['trigger_name_null']:,} native clips with null trigger_name; "
          f"{warts['trigger_name_lowercased']:,} with lower-cased trigger_name; {warts['duration_null']:,} null duration_s; {warts['clock_skew_rows']} rows with deleted_ts < captured_ts",
          f"- clips.csv: deleted_14d / shared_14d are NULL for clips captured after {(AS_OF - D(14)).date()} (censored, not zero)",
          f"- players.csv: country null on {int(P.country.isna().sum()):,} rows",
          "- game_daily.csv: Rocket League row for 2026-07-04 missing (pipeline outage); clips_deleted_distinct is client-side (× 4/3 vs server rows) and any-age",
          "- studio_daily.csv: Ghost Janitors 2026-06-30 appears twice; *_change columns are day-over-day diffs (noise), not velocity",
          "- platform.csv: delete_events / share_events are EVENTS (× 1.05 / × 1.35 of distinct clips); our six games are scaled × 40 to platform size",
          "- Steam-achievement auto-clips exist for all steam_linked players throughout (generic hook predates the window); only 8% of RL players are steam_linked",
          ]
    return "# Answer key — synthetic Medal dataset\n\nOpen only after the mock. PLANTED = constant in generate_medal.py; realized = computed from the generated rows.\n\n" + "\n".join(L) + "\n"


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(HERE / "out"))
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    out = Path(a.out)
    (out / "packet").mkdir(parents=True, exist_ok=True)

    P = make_players(rng)
    S = make_sessions(P, rng)
    C = make_clips(S, rng)
    GD = game_daily(S, C)
    O14 = outcomes_14d(C)
    TB = trigger_breakdown(C)
    RR, RRD = return_rate(S, C)
    LC = launch_cohort(P, S, C)
    E = studio_daily(S, C, rng)
    SM = studio_monthly(P, S, C, rng)
    PL = platform_table(GD, rng)
    W = weekly_panel(GD)

    players_out, deleted = wart_players(P, rng)
    sessions_out = wart_sessions(S)
    clips_out, warts = wart_clips(C, rng)
    gd_out, e_out = wart_game_daily(GD), wart_studio_daily(E)

    games_out = pd.DataFrame([dict(game_id=g["game_id"], game_name=g["name"], studio_id=g["studio_id"], business_model=g["model"], store=g["store"],
                                   autoclip_launch_date=g["launch"].date() if g["launch"] is not None else None, session_unit=g["unit"],
                                   release_date=GJ_RELEASE.date() if g["game_id"] == 2 else None) for g in GAMES])
    studios_out = pd.DataFrame(STUDIOS).assign(integration_live=lambda x: x.integration_live.map(lambda v: v.date() if pd.notna(v) else None))

    def w(name, df):
        df.to_csv(out / f"{name}.csv", index=False)
        print(f"  {name:<28} {len(df):>8,} rows × {df.shape[1]:>2} cols")
    print(f"writing {out}")
    w("games", games_out); w("studios", studios_out); w("players", players_out); w("sessions", sessions_out); w("clips", clips_out)
    w("player_launch_cohort", LC); w("game_daily", gd_out); w("outcomes_14d_by_trigger", O14); w("trigger_breakdown", TB)
    w("return_rate", RR); w("return_rate_player_days", RRD); w("studio_daily", e_out); w("studio_monthly", SM); w("platform", PL); w("game_weekly_panel", W)

    # packet-shaped copies with the Legend's exact column names, so the live /medal-autoclip skill parses them
    pk = out / "packet"
    for key, gid in (("rl", 1), ("gj", 2)):
        gd_out[gd_out.game_id == gid].drop(columns="game_id").assign(date=lambda x: x.date.dt.date).to_csv(pk / f"{key}_daily.csv", index=False)
        O14[O14.game_id == gid].drop(columns="game_id").assign(week=lambda x: x.week.dt.date).to_csv(pk / f"{key}_14d_outcomes.csv", index=False)
        TB[TB.game_id == gid].drop(columns="game_id").to_csv(pk / f"{key}_trigger_breakdown.csv", index=False)
        RR[RR.game_id == gid].drop(columns="game_id").to_csv(pk / f"{key}_return_rate.csv", index=False)
    PL.to_csv(pk / "platform.csv", index=False)
    e = e_out[e_out.game_id == 2].assign(date=lambda x: x.date.dt.date)
    e[["date", "ccu_peak", "ccu_avg"]].rename(columns={"ccu_peak": "Players", "ccu_avg": "Average Players"}).to_csv(pk / "gj_ccu.csv", index=False)
    e[["date", "copies_sold", "copies_sold_change"]].rename(columns={"copies_sold": "Copies Sold", "copies_sold_change": "Copies Sold Change"}).to_csv(pk / "gj_copies_sold.csv", index=False)
    e[["date", "wishlists", "wishlists_change"]].rename(columns={"wishlists": "Wishlists", "wishlists_change": "Wishlists Change"}).to_csv(pk / "gj_wishlists.csv", index=False)
    e[["date", "dau"]].rename(columns={"dau": "DAU"}).to_csv(pk / "gj_dau.csv", index=False)
    print(f"  packet/                       13 Legend-shaped CSVs for /medal-autoclip")

    key = answer_key(P, S, C, RRD, LC, GD, E, warts, deleted)
    (out / "answer_key.md").write_text(key)
    print(f"  answer_key.md                 (open only after the mock)")

    try:
        import duckdb
        db = out / "medal.duckdb"
        if db.exists():
            db.unlink()
        con = duckdb.connect(str(db))
        for p in sorted(out.glob("*.csv")):
            con.execute(f"CREATE TABLE {p.stem} AS SELECT * FROM read_csv_auto('{p}', header=true)")
        n = con.execute("SELECT count(*) FROM information_schema.tables").fetchone()[0]
        con.close()
        print(f"  medal.duckdb                  {n} tables")
    except Exception as ex:  # noqa: BLE001
        print(f"  (duckdb skipped: {ex})")


if __name__ == "__main__":
    main()
