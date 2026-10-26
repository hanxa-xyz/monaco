# datasets/medal — synthetic Medal auto-clipping dataset

Rehearsal data for the Medal.tv live case (auto-clipping impact on **Rocket League** and **Ghost Janitors**) and for the
General Intuition angle (which clips are useful training data). Row-level tables are generated from a small set of
**planted truths**; every aggregate is rolled up from those rows, so the dataset reconciles with itself except where a wart is
planted on purpose. The realized magnitudes are written to `out/answer_key.md` — open it only after a mock.

```bash
python3 datasets/medal/generate_medal.py            # ~4 s; writes datasets/medal/out/ (gitignored)
python3 datasets/medal/generate_medal.py --seed 11  # a fresh draw; the planted constants stay the same
```

Python 3.9 / numpy / pandas only. DuckDB is optional (`out/medal.duckdb` with all 15 tables is written when it imports).

## Window and launches

| | |
|---|---|
| Row-level window | 2026-02-01 → 2026-08-31 (212 days); observation stops 2026-09-01, so 14-day outcomes are **censored** for clips captured after Aug 18 |
| Rocket League auto-clip launch | 2026-05-07 (Thu) · free-to-play, Epic store; only 8% of RL players are Steam-linked |
| Ghost Janitors auto-clip launch | 2026-05-21 (Thu) · paid indie, Steam-only, released 2025-11-08 (post-release decay runs through the window) |
| Client ramp | each player's client updates 0–9 days after launch (`sessions.autoclip_on` turns on then) |
| Randomized holdout | **20% of each launched game's players never get auto-clips** (`players.autoclip_holdout = 1`) |
| Controls | Valorant (auto-clip live since 2025-09, always treated), Marvel Rivals, Phasmophobia, Lethal Company (never treated) |

The row-level sample is roughly a 1/40 slice of each game's Medal population; `platform.csv` scales our six games back up (×40)
next to 13 context games.

## Tables (`out/*.csv`)

| table | one row = | rows | notes |
|---|---|---|---|
| `games` | a game | 6 | studio, business model, store, `autoclip_launch_date` (null = never) |
| `studios` | a partner studio | 6 | tier, `integration_live`, `triggers_configured` |
| `players` | a Medal user (primary game) | ~5.6k | signup, country (4% null), premium, `steam_linked`, **`autoclip_holdout`**; 15 accounts deleted → orphans |
| `sessions` | a player × game × day session | ~65k | `start_ts`, `duration_min`, `units_played` (matches / rounds), **`autoclip_on`** (0/1 that day), `events_fired` (trigger events the game sent; ~3% don't capture) |
| `clips` | a clip | ~125k | `trigger_class` (hotkey · autoclip_native · autoclip_steam_achievement), `trigger_name`, `deleted_ts`, `shared_ts`, `posted_public`, **`deleted_14d` / `shared_14d`** (null when censored), media: `duration_s`, `resolution`, `fps`, `input_log_attached`, `motion_score`, `storage_mb` |
| `player_launch_cohort` | a player active in the 28 days before their game's launch | ~2.1k | the A/B table: `autoclip_holdout`, pre-28d covariates (sessions, minutes, manual clips, shares), 14-day outcomes, `got_autoclip_14d`, `retained_d14_27`, `retained_d28_41` |
| `game_daily` | a game × day | 1,271 | the packet's **Daily (per game)** columns, Legend names verbatim; RL 2026-07-04 missing |
| `outcomes_14d_by_trigger` | a game × capture-week × trigger_class | 365 | packet **14D outcomes by trigger**; last two weeks dropped (censoring) |
| `trigger_breakdown` | a game × trigger_name (post-launch) | 18 | packet **Trigger breakdown** |
| `return_rate` / `return_rate_player_days` | aggregate / a player-day from launch+10 to Jul 26 | 4 / ~14k | packet **Return rate**: `got_autoclip`, `returned_wk2` (d+7…13), `returned_wk5` (d+30…36) |
| `studio_daily` | a game × day for the two paid partners sharing data (GJ, Lethal Company) | 425 | `dau`, `ccu_peak`, `ccu_avg`, `copies_sold`, `wishlists`, the day-over-day `*_change` columns; GJ 2026-06-30 duplicated |
| `studio_monthly` | a studio × month | 42 | partner-health grain: Medal players, auto-clips, shares, est. off-platform views, `api_errors`, `support_tickets`, `integration_live` |
| `platform` | a game (platform-wide, Feb 1 – Aug 31) | 19 | packet **Platform**: `clips_autoclip`, `delete_events` / `share_events` (events, not distinct clips), monthly avg players / clippers |
| `game_weekly_panel` | a game × week | 186 | DiD input: `treated`, `post`, `manual_per_player_day`, `shares_per_player_day`, `share_per_clip` |

`out/packet/` holds 13 Legend-shaped CSVs (`rl_daily.csv`, `gj_14d_outcomes.csv`, `gj_dau.csv`, …) that the ds-interviews
`/medal-autoclip` loader parses as a packet folder.

## Planted effects (constants in `generate_medal.py`; realized values in `out/answer_key.md`)

| effect | Rocket League | Ghost Janitors |
|---|---|---|
| hotkey clips per session, auto-on vs holdout | **−12%** (cannibalization) | **0%** |
| daily play probability, auto-on vs holdout | **+2%** | **+5%** |
| native auto-clips per session (post, on) | ~2.3 (0.45 per match) | ~1.0 (0.30 per round) |
| 14-day delete / share by trigger | junk: Demolition, Assist, Save (55–62% deleted, ≤1.5% shared) · keepers: Aerial Goal, Epic Save (≤22% deleted, 6–8.5% shared) · Goal = volume, middling | junk: Generator Blackout, Job Complete · keepers: Brutal Jump Scare (14% shared), Team Wipe |
| hotkey / steam-achievement clips | delete 12% / 22%, share 9.5% / 5.5% (before tier multipliers) | same |
| Medal penetration of studio DAU | n/a (Epic shares no DAU — ask for it) | **7%** |
| studio funnel per auto-clip share (lag 0–3 d) | n/a | **1.5 wishlists, 0.30 copies** → a few % of the post-launch totals: underpowered by design |
| calendar confounds | RLCS Paris Major May 20–26 (+6% players, +15% hotkey clips), in-game season Jun 10 (+10%, decaying), summer from mid-June, weekends +18% | launch-week **25% discount May 21–27** (copies ×~3, DAU +25%), content patch Jun 4 (+30% DAU, decaying), Steam Spring Sale Mar 19–26, Summer Sale Jun 25–Jul 9, post-release decay |
| selection trap | engagement tier (latent) drives session length → trigger events → `got_autoclip`, and also return rates: the naive got-vs-not gap is ~20 pp against a true effect of a few pp | same |
| client vs server deletions | daily `clips_deleted_distinct` = server rows × 4/3 and any-age; a **bulk purge of old clips Jun 15–18** (client "free up space" prompt) | — |

Everything with a number in it that the analyst might quote (penetration, trigger rates, incremental copies, the A/B contrasts
with standard errors) is recomputed from the generated rows in `answer_key.md`, next to the planted constant.

## Data-quality warts (exact counts in the key)

exact duplicate clip rows (~1.2%) · 15 deleted accounts → orphan sessions and clips · null `trigger_name` on 2% of native clips
and lower-cased names on 3% (old client build) · 1% null `duration_s` · 30 clips with `deleted_ts < captured_ts` (clock skew) ·
`country` null 4% · RL `game_daily` row for Jul 4 missing · GJ `studio_daily` Jun 30 duplicated · `*_change` columns are
diffs, not velocity · platform `*_events` are events, not distinct clips · censored 14-day flags are null, never zero.

## How the tables answer the case

- **Data volume / cannibalization** → `game_daily` (manual = total − native − steam) or `sessions` ⋈ `clips`; the clean read is `player_launch_cohort` (holdout) or the weekly panel (DiD vs controls).
- **Dilution** → shares per clip falls while shares per player-day rises; both are in `game_daily` and the panel.
- **Clip quality / junk triggers** → `clips` by `trigger_name` with `deleted_14d` / `shared_14d`; aggregated in `trigger_breakdown`.
- **Retention** → `return_rate` reproduces the packet's biased read; `player_launch_cohort` gives the holdout contrast with pre-period covariates for CUPED / regression adjustment.
- **Studio impact** → `studio_daily` for GJ vs Lethal Company (control), per-DAU normalization, and the plausibility ceiling (Medal reaches 7% of DAU).
- **Partner health** → `studio_monthly` for concentration, launch-month error spikes, per-partner trends.
- **General Intuition** → `clips` media columns: a "useful clip" is kept (not deleted), has `input_log_attached`, high `motion_score`; storage cost is `storage_mb`.

## Nine notebooks: six answers to Case 1, three for Case 2 (`nb/`)

Builders in `nb/`, outputs in `out/notebooks/`; each runs in 10–40 s. Shared helpers in `nb/medal_nb.py` (projected
baseline, Wilson rate tables, two-arm tables, synthetic control + placebos, E-value, MDE grid with design effect, sizing dials,
house-grammar charts). Every notebook ends with the five-line close and a limits section.

**Case 1 — "assess the impact of auto-clipping" — one question, six identification routes** (the ladder from weakest to strongest
is 01 → 04 → 05 → 03 → 02; 06 ranks hypotheses for all of them):

| notebook | approach | uses | Rocket League cannibalization read |
|---|---|---|---|
| `01_packet_prepost` | packet-only: log-linear + weekday baseline projected over days 14–41; per-player rates; spike exclusion; plausibility ceiling; pruning curve | packet tables | −3% "within noise" (planted −12%: short window, holdout dilution) |
| `02_holdout_ab` | randomized 20% holdout: balance, ITT, CUPED, selection trap, weekly arms, heterogeneity, row-level trigger quality, MDE | cohort, sessions, clips | −11% (DiD on the weekly arms) |
| `03_did_controls` | never-treated games as controls: 2×2 DiD, event study + pre-trend test, placebo, studio DiD with week-level SE, Kaplan-Meier | weekly panel, studio_daily, clips | −11% (CI −13…−10, pre-trend p 0.55) |
| `04_synthetic_control` | donor-weighted counterfactual on indexed daily series; in-space and in-time placebos | game_daily | −5.5%, rank 1/5 among placebos (4 donors: under-recovers) |
| `05_ipw_got_autoclip` | propensity / IPW on "got a clip" with pre covariates; overlap, balance, E-value; compared with the holdout it cannot see | cohort | retention: naive +29 pp → IPW +8 pp → randomized +3.5 pp |
| `06_model_hypotheses` | RF + XGB on clip shares and player retention; tripwire; PDPs; hypotheses mapped to the designs above | clips, cohort | pre-launch activity dominates retention; arm ≈ 0 importance |

**Case 2 — the three most likely 20-minute prompts:**

| notebook | prompt | what it produces |
|---|---|---|
| `07_experiment_design` | design the next rollout | the brief (hypothesis, primary, guardrails, unit, exposure, analysis, stopping), MDE grid by holdout share × weeks × ICC, horizon table (accrual + 4 weeks maturation) |
| `08_next_integration` | which game next, how big | dials per candidate (players × sessions × triggers × keep × share), two routes to the number, concentration, storage cost, paid-game copies at two rates, ranked shortlist |
| `09_useful_clip_northstar` | what is a useful clip (GI); north star | useful = kept ∧ labelled ∧ motion ≥ 0.5 with threshold sensitivity; penetration by trigger; junk storage cost; deleted-clips argument both ways; six north-star candidates tested pre/post |

```bash
for n in 01_packet_prepost 02_holdout_ab 03_did_controls 04_synthetic_control 05_ipw_got_autoclip 06_model_hypotheses 07_experiment_design 08_next_integration 09_useful_clip_northstar; do python3 datasets/medal/nb/build_$n.py | tail -1; done
```

Where the Case 1 notebooks disagree in size, trust 02 (randomized) over 03 (controls) over 04 (synthetic) over 05 (IPW) over 01
(projection). The agreement in sign across all of them is the argument to make in the room.
