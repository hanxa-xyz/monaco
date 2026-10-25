# Medal / General Intuition live case — problems, skill coverage, gaps

Written 2026-10-25 against `datasets/medal/out/` (seed 7). Every claim about a skill comes from its SKILL.md or the module it
calls; every "worked / broke" line is from a run in this session.

## What was run, what happened

| run | command | result |
|---|---|---|
| generator | `python3 datasets/medal/generate_medal.py` | 15 tables + 13 packet CSVs + answer key + DuckDB in ~4 s |
| `/eda` | `python3 datasets/medal/build_eda_medal.py` | `EXECUTED OK` in 8 s; 13 figures, 0 cell errors; structure view caught the duplicate `clip_id` rows |
| `/medal-autoclip` | `/opt/anaconda3/bin/python ds-interviews/.claude/skills/medal-autoclip/scripts/run.py datasets/medal/out/packet --out datasets/medal/out/medal_live` | parse report found all 13 tables; scorecards, two draft closes, 10 figures, executed notebook in 9 s |
| `/causal` CLI | `monaco-did --csv game_weekly_panel.csv --cols unit=game_name,period=week,y=manual_per_player_day --treated-units "Rocket League" --treat-period 2026-05-04 --window=-8,8` | **2×2 worked**: ATT −0.145 hotkey clips per player-day on a treated pre-level of 1.36 (−11%; planted −12% on treated players, −9.6% after 20% holdout dilution), SE 0.02 with the single-treated-unit caveat printed. **Three bugs**: (i) `--treated-units 1` stays a string while `game_id` is int → 0 treated → `KeyError: 1` in `plot_did` (use a string unit column); (ii) `--window -8,8` must be `--window=-8,8`; (iii) the event study crashes on weekly date periods from CSV (`np.searchsorted(periods, treat_period)` compares int to Timestamp in `causal.event_study`), so no pre-trend test. The header also prints `outcome = kyc7` for any `--cols y=…` mapping. |
| `/survival` CLI | `monaco-survival --csv clips.csv --cols entity_id=clip_id,group=trigger_class,start=captured_ts,end=deleted_ts --as-of 2026-09-01 --marks 1,7,14 --tau 30` | **worked but took 6 min** on 124k clips (fractional-day durations → ~100k distinct event times in `km()`); unusable live. Output is right: S14 hotkey 0.91 vs native auto-clip 0.66 vs steam 0.83, log-rank χ² 12,809, naive-vs-KM gap 1 pp (censoring is 77% because deletions are rare). Floor durations to whole days or sample ≤ 30k rows: the same command on a 15k-clip sample took 8 s. |

What the live skill got right on this data: dilution (shares/clip −47%, shares/player +38%), the June purge excluded from the
deletion fit, Demolition/Assist flagged junk, RLCS Major flagged inside the RL post window, the GJ reach ceiling and
break-even printed. What it got wrong, and why it matters: it declared Ghost Janitors a **studio case study** on
wishlists-per-DAU +15% (the planted incremental share is 7.7% and the launch week carries a 25% discount), it read RL manual
clips/player as "within noise −3%" (planted −12% on treated players; diluted by the 20% holdout and under-powered at 28-day
windows), and it closed with "revisit with a 10% holdout" while the data contains a 20% holdout it never looks at.

## (a) The problems the interview most likely asks, (b) what answers each today

Ranked by likelihood. "Invocation" is what to type or run in the room; `…` = the path to the packet or table.

| # | problem (Medal unless marked GI) | skill today | exact invocation | coverage |
|---|---|---|---|---|
| 1 | What is in the packet; grain, nulls, dupes, date ranges | `/medal-autoclip` parse report; `/eda-structure` | `run.py … --no-nb` (first 20 lines) · `structure({'clips': clips, 'sessions': sessions}, keys={'clips': [['clip_id']], 'sessions': [['session_id'], ['player_id','game_id','session_date']]})` | full |
| 2 | Did auto-clipping grow data volume, and did it cannibalize hotkey clips? | `/medal-autoclip` scorecard (ITS vs projected baseline, per-player rates) | `run.py … --out …` → "Manual clips / player" row | partial: no holdout read, no control-game DiD (see gaps 1, 2) |
| 3 | Share rate per clip fell — is engagement down? (dilution) | `/medal-autoclip` | same run → "Shares / clip" vs "Shares / player" rows and `fig_rates` | full |
| 4 | Which triggers are junk; what to prune; volume vs shares trade | `/medal-autoclip` triggers view; `/eda-penetration` | same run → Triggers table + `fig_quality` · `penetration(clips, 'trigger_name', 'deleted_14d')` | mostly: no trade-off curve (gap 4) |
| 5 | Does auto-clipping improve retention? | `/medal-autoclip` return-rate view (prints the gap and the selection caveat only) | same run → "Return rate: wk2 gap" | weak: no estimate at all (gap 1) |
| 6 | Did it move Ghost Janitors wishlists / copies? Can the studio quote it? | `/medal-autoclip` external view (per-DAU, spike exclusion, plausibility ceiling, break-even) | same run → External block + `fig_external` | partial: pre/post only; over-claims when a discount and a patch sit in the window (gap 2) |
| 7 | Design the next rollout: default-on vs opt-in, unit, metrics, duration (Case 2) | none (prose from `background.md`) | — | gap 3 |
| 8 | Which game gets the next integration? Size it (Case 2) | `/takehome-sizing` (discipline, no code); platform table | `run.py` Platform block for the candidate list | gap 5 |
| 9 | GI: which clips are useful training data; what does junk cost in storage | `/eda` (penetration of `input_log_attached` / `kept_14d` by trigger, pareto of `storage_mb` by player); `/model` | `build_eda_medal.py` (swap `flag`) · `run_pipeline(clips, 'shared_14d', exclude=['clip_id','session_id','player_id','deleted_ts','shared_ts','deleted_14d'], time_col='captured_ts')` | partial: no "useful clip" definition view or $/GB sizing (gap 6) |
| 10 | How fast do clips die, by trigger class (time-to-delete with censoring) | `/survival` | `monaco-survival --csv clips.csv --cols entity_id=clip_id,group=trigger_class,start=captured_ts,end=deleted_ts --as-of 2026-09-01 --marks 1,7,14` | works on a sample only (gap 7) |
| 11 | Studio scorecard across partners: who is slipping, concentration | `/partner-health` | needs the brokerage contract (`kyc7_n`, `fund30_k`, deposits…) — `studio_monthly` cannot be mapped with `--cols` alone | gap 8 |

## (c) Gaps, ranked by how likely they come up

1. **Holdout / A-B read (very likely, problems 2 and 5).** Nothing consumes `player_launch_cohort`. Needed: one view that
   prints, per game, auto-on vs holdout for hotkey clips/session, shares/player, sessions/player and `retained_d14_27` with
   Wilson / t intervals, plus the CUPED-adjusted version using `pre28_sessions` / `pre28_manual_clips`. The estimator exists
   (`monaco.causal.cuped(df, y, y_pre, arm)`); what is missing is the cohort-table contract, the chart (penetration-style
   bars, on vs holdout, per metric) and a `/medal-autoclip --cohort cohort.csv` or `/causal --ab` entry. The same view should
   print the naive `got_autoclip_14d` gap next to it, which is the selection trap in one picture.
2. **Control-game difference-in-differences (likely, problems 2 and 6).** `monaco.causal.did` and `event_study` exist and the
   CLI runs on `game_weekly_panel.csv` once the unit column is a string. Gaps: (i) `cli_did` should coerce `--treated-units` to
   the unit column's dtype; (ii) a studio-side panel (GJ vs Lethal Company on `studio_daily`, weekly, `wishlists_per_dau`) is not
   produced by anything — the live skill should build it when a second external feed is present; (iii) the live skill's
   close should downgrade "studio case study" when a sale-like spike or a DAU shock overlaps the post window (it already
   detects both and still said GO).
3. **Experiment design / power (likely as Case 2).** No skill. Needed: an MDE table from the data's own base rates (14-day
   return ≈ 55%, share rate ≈ 10%, sessions/player) for holdout shares of 5/10/20/50% and 2/4/8 weeks, and the party-spillover
   note (co-op games randomize by party or by game, not by user). ~40 lines over `monaco.stats`.
4. **Pruning trade-off curve (likely, problem 4).** Triggers sorted by share rate; cumulative % of auto volume removed vs % of
   auto shares and deletions lost. The live skill prints the two numbers for the junk set; the curve lets the interviewer pick
   the threshold.
5. **Integration sizing view (Case 2).** `Medal players × trigger rate × keep rate × share rate` as dials, using `platform.csv`
   for the candidate list and `trigger_breakdown` for the rates; `/takehome-sizing` has the discipline but no code.
6. **"Useful clip" view for GI (medium).** Define useful = kept 14d × `input_log_attached` × `motion_score ≥ x`; penetration
   by trigger and by game; storage of useful vs junk (`storage_mb`) and $/GB sensitivity. `/eda` can draw each piece; the
   composite flag and the cost line are missing.
7. **Survival at 100k+ rows (medium).** `km()` iterates over distinct event times; durations should be floored to the unit
   (`--unit D` → integer days) or the CLI should sample above ~30k rows and say so. Until then: sample first.
8. **Partner-health on a non-brokerage grain (low for Medal, high for a "studio scorecard" prompt).** `partner_health.REQUIRED`
   hard-codes the brokerage metric names. A generic contract (`partner_id, month, entities_new, rate1_n, rate1_k, …, volume`)
   or an alias layer would let `studio_monthly` run through concentration, trends and early-warning flags unchanged.
9. **Notebook extension (process, see d).** No skill can add a section to an existing notebook; see below.

Convention gaps noticed on the way: `/eda` writes to `companies/<c>/scripts/…` and `/takehome-kickstart` hard-codes the
ds-interviews path; neither has a home for a dataset that lives in monaco (`datasets/<name>/`). The medal-autoclip skill
imports `dsviz` from `ds-interviews/toolkit`, not from `monaco.viz`, and runs on the anaconda Python (3.12), while monaco
runs on the system 3.9.

## (d) Two questions about the notebooks, answered from the skill files

**Do the skills generate separate notebooks per theme?** Mostly no.

- `/eda` builds **one** notebook, `notebooks/eda_views.ipynb`, with one section per view in the fixed order
  (`eda_build.build_from_spec`: "one section per view"). The per-view skills (`/eda-penetration`, …) are entries into that
  same vocabulary, not separate notebooks; live they are meant to be called "directly in a scratch cell".
- `/model` is explicit: "One notebook per company (`notebooks/model.ipynb`), several targets inside; do not fork per target."
- `/medal-autoclip` builds one `medal_live.ipynb` with a section per game and a Scratch cell at the end.
- `/takehome-notebooks` is the exception: a menu of four themed notebooks, "numbered `NN_name.ipynb`", each from its own
  builder script, and notebooks 2–4 import notebook 1's feature table.
- `/causal`, `/survival`, `/funnel-cohort`, `/partner-health` produce no notebook: `readout.md` + `figs/` + CSVs.

**Can a skill modify a notebook whose theme already exists rather than regenerating it?** No, by design.
Every builder starts from `new_notebook()` and ends in `build_and_execute(nb, path)`, which overwrites the file and re-executes
all cells; the rule repeated in `/eda`, `/takehome-eda`, `/takehome-kickstart`, `/takehome-notebooks` and `AGENTS.md` is
"never hand-edit the .ipynb; edit the builder and re-run". There is no load-existing-notebook path in `monaco.viz` or
`monaco.eda_build`, and no skill reads a notebook back. The only "add to it" affordance is the human Scratch cell.

In practice the regenerate path is cheap here (8 s for `/eda` on 125k clips), so the live move is: add the dimension or flag
to the SPEC, re-run the same builder to the same path. What would have to change for true in-place extension:

1. `monaco.viz.extend_notebook(path, cells, section_id)`: `nbformat.read` the existing notebook, replace the cells tagged
   `section_id` or append after the last view section, re-execute (whole notebook, or only the new cells via
   `NotebookClient.execute_cell`), write back.
2. Builders tag every cell with its id (`cell.metadata.tags = ['view:penetration:trigger_name']`) so a section is addressable.
3. Persist the SPEC beside the notebook (`eda_views.spec.json`) so `/eda-<view>` invoked later can diff it and add exactly one
   (view, dimension) instead of asking for the whole SPEC again.
4. One sentence in each SKILL.md procedure: "if the notebook exists, extend it; regenerate only when the SPEC's entity or
   metric changed." Roughly 60 lines of code plus one test; the chart-grammar rule "one chart per (view, dimension)" is
   preserved because the section id is the (view, dimension) pair.

## Three worked answers (added after the gap list)

`nb/build_01_packet_prepost.py`, `nb/build_02_holdout_ab.py`, `nb/build_03_did_controls.py` answer the case three ways on this
data (see README). They are notebooks, not skills: they demonstrate gaps 1–4 and 7 (holdout + CUPED view, control-game DiD
with a working event study via an integer week index, the MDE table, the pruning curve, KM on a 20k sample) without yet
packaging them. Converting their cells into `monaco` functions + SKILL.md entries is the build list below.

## Suggested order to build (not started here)

Gap 1 (holdout + CUPED view) → gap 2(i)+(iii) (cli_did dtype fix, close downgrade) → gap 3 (MDE table) → gap 4 (prune
curve). Together they cover problems 2, 4, 5, 6 and the most likely Case 2 prompt. Gaps 6–8 after the Medal round.
