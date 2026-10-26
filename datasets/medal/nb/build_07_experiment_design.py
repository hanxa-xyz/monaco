"""Notebook 07 — Case 2 prompt: "design the next auto-clip rollout as an experiment".

    python3 datasets/medal/nb/build_07_experiment_design.py   ->  datasets/medal/out/notebooks/07_experiment_design.ipynb
"""
from pathlib import Path

from monaco.viz import build_and_execute, code, md, new_notebook

NB = Path(__file__).resolve().parent
OUT = NB.parent / "out" / "notebooks"
nb = new_notebook(); C = nb.cells

C.append(md("""# Medal auto-clipping — 07 · Case 2: design the next rollout

**Likely prompt:** *"We are integrating auto-clipping with the next studio. Design the experiment: default-on vs opt-in, what
to randomize, what to measure, how long."* Twenty minutes, so the deliverable is a one-page brief with numbers from the two
launches we have.

Everything numeric here comes from the data: base rates from `player_launch_cohort` and `sessions`, the share-of-players-per-
week accrual from the launch cohorts, variances for the count outcomes. The one input the data cannot give is the intra-party
correlation of outcomes (we do not observe parties); it is carried as a dial."""))

C.append(md("## 0 · Setup and the base rates the design needs"))
C.append(code(r"""import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0, '__NBDIR__')
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from IPython.display import Markdown, display
import medal_nb as mn
mn.setup()
T = mn.load('player_launch_cohort', 'sessions', 'players', 'clips')
coh = T['player_launch_cohort']; coh['game'] = coh.game_id.map(mn.NAME)
ho = coh[coh.autoclip_holdout == 1]
BASE = ho.groupby('game').agg(n_holdout=('player_id', 'size'), retention_d14_27=('retained_d14_27', 'mean'), sessions_14d=('post14_sessions', 'mean'), sessions_14d_sd=('post14_sessions', 'std'),
                               manual_clips_14d=('post14_manual_clips', 'mean'), manual_clips_14d_sd=('post14_manual_clips', 'std'), shares_14d=('post14_shares', 'mean'), shares_14d_sd=('post14_shares', 'std'),
                               deletes_14d=('post14_deletes', 'mean'))
print('base rates from the HOLDOUT arms (what a control group looks like in the first 14 days):'); print(BASE.round(3).to_string())
S = T['sessions']; P = T['players'][['player_id', 'signup_date']]
eligible = P.merge(S.groupby('player_id').game_id.first().reset_index(), on='player_id')
print('\neligible population per game (any session in the window, sample scale):'); print(eligible.groupby('game_id').size().rename(index=mn.NAME).to_string())"""))

C.append(md("## 1 · The brief: hypothesis, primary metric, guardrails, unit"))
C.append(code(r"""brief = pd.DataFrame([
    ('Hypothesis', 'Default-on auto-clipping raises kept-and-shared clips per player without reducing hotkey clipping or 14-day return.'),
    ('Primary metric', 'players with ≥1 kept-or-shared clip in days 0–13 after exposure (binary per player) — moves with the feature, not mechanical'),
    ('Secondary', 'shares per player (count), kept auto-clips per player, 14-day return (days 14–27)'),
    ('Guardrails', 'hotkey clips per session (−10% stops the test), deletions per player (+100% flags curation burden), storage GB per player'),
    ('Arms', 'default-on (treated) vs off (control); opt-in as a third arm only if the studio insists — it measures uptake, not effect'),
    ('Unit', 'player for solo games; party/lobby for co-op (holdout players in treated lobbies see friends\' clips → spillover dilutes the contrast)'),
    ('Eligibility', 'players with ≥1 session in the 28 days before launch (existing) and new signups (separately — different base rates)'),
    ('Exposure', 'client updated and feature flag on; analyse by assignment (ITT), report compliance'),
    ('Analysis', 'difference in means with CUPED on the same metric from the 28 days before; Wilson/t intervals; pre-registered'),
    ('Stopping', 'fixed horizon chosen from the MDE grid below; one interim look at half the horizon with a Pocock-style threshold (p < 0.03), otherwise no peeking'),
], columns=['item', 'decision'])
print(brief.to_string(index=False))"""))

C.append(md("## 2 · MDE grid: holdout share × weeks × design effect, from the data's own base rates"))
C.append(code(r"""SCALE = 40                              # row-level sample ≈ 1/40 of the real Medal population per game
WEEKLY_FRAC = 0.45                      # share of the eligible population observed in any given week (from the sessions table below)
act = S.assign(week=S.session_date - pd.to_timedelta(S.session_date.dt.dayofweek, unit='D')).groupby(['game_id', 'week']).player_id.nunique() / eligible.groupby('game_id').size()
print('share of eligible players active per week, median by game:'); print(act.groupby('game_id').median().rename(index=mn.NAME).round(3).to_string())
G = {}
for g in ('Rocket League', 'Ghost Janitors'):
    gid = 1 if g == 'Rocket League' else 2
    n_total = int(eligible.groupby('game_id').size()[gid] * SCALE)
    b = BASE.loc[g]
    grid_r = mn.mde_grid(b.retention_d14_27, n_total, [0.5, 0.2, 0.1, 0.05], [2, 4, 8], float(act.groupby('game_id').median()[gid]), icc=(0.0, 0.05, 0.10), cluster_size=3 if gid == 2 else 1)
    grid_s = mn.mde_grid(b.shares_14d, n_total, [0.5, 0.2, 0.1, 0.05], [2, 4, 8], float(act.groupby('game_id').median()[gid]), icc=(0.0, 0.05, 0.10), cluster_size=3 if gid == 2 else 1, sd=b.shares_14d_sd)
    G[g] = (grid_r, grid_s)
    print(f'\n== {g}: eligible ≈ {n_total:,} players at platform scale; retention base {b.retention_d14_27:.1%}; shares/player base {b.shares_14d:.2f} (sd {b.shares_14d_sd:.2f}); cluster size {3 if gid == 2 else 1}')
    show = grid_r[grid_r.icc.isin([0.0, 0.10])].pivot_table(index=['weeks', 'holdout_share'], columns='icc', values='mde').rename(columns=lambda c: f'retention MDE pp (icc={c})') * 100
    show2 = grid_s[grid_s.icc == 0.0].pivot_table(index=['weeks', 'holdout_share'], values='mde_rel').rename(columns={'mde_rel': 'shares/player MDE (relative)'})
    print(pd.concat([show, show2], axis=1).round(2).to_string())
fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
for ax, g in zip(axes, ('Rocket League', 'Ghost Janitors')):
    gr = G[g][0]
    for sc, col in zip([0.5, 0.2, 0.1, 0.05], [mn.BLACK, mn.O_DARK, mn.O_MID, mn.O_LIGHT]):
        s = gr[(gr.holdout_share == sc) & (gr.icc == 0.0)]; ax.plot(s.weeks, s.mde * 100, marker='o', color=col, lw=1.8, label=f'holdout {sc:.0%}')
        s2 = gr[(gr.holdout_share == sc) & (gr.icc == 0.10)]; ax.plot(s2.weeks, s2.mde * 100, marker='o', color=col, lw=1, ls=':')
    ax.axhline(3, color=mn.GRAY, ls='--', lw=1); ax.text(2, 3.1, ' 3 pp = the effect size worth a decision', color='#666', fontsize=8)
    ax.set_xlabel('weeks of accrual'); ax.set_ylabel('MDE on 14-day retention (pp)'); ax.set_xticks([2, 4, 8])
    mn.titled(ax, f'{g}: smallest detectable retention effect', 'solid = player randomization · dotted = party randomization with ICC 0.10 · 80% power, α 5%')
axes[0].legend(fontsize=8)
fig.tight_layout(); plt.show()"""))

C.append(md("## 3 · Duration and the stopping rule"))
C.append(code(r"""rows = []
for g, (gr, gs) in G.items():
    for sc in (0.2, 0.1, 0.05):
        ok = gr[(gr.holdout_share == sc) & (gr.icc == (0.10 if g == 'Ghost Janitors' else 0.0)) & (gr.mde <= 0.03)]
        acc = int(ok.weeks.min()) if len(ok) else None
        rows.append(dict(game=g, holdout_share=sc, accrual_weeks=acc if acc else '> 8', outcome_maturation_weeks=4, horizon_weeks=(acc + 4) if acc else '> 12',
                         design='party, ICC 0.10' if g == 'Ghost Janitors' else 'player'))
DUR = pd.DataFrame(rows); print(DUR.to_string(index=False))
print('\nhorizon = weeks to accrue enough exposed players + 4 weeks for the last of them to reach day 27 (retention window d14–27 after exposure).')
print('\nRule: fix the horizon from this table before launch; one interim look at the halfway point at p < 0.03; final read at p < 0.045; report the CUPED estimate with its interval, not the p-value alone.')
print('Novelty: the first two weeks are the client ramp and a novelty bump (see 03 event study) — the primary read is weeks 3+, the ramp weeks are reported separately.')"""))

C.append(md("## 4 · What the two launches already tell us the test will find"))
C.append(code(r"""rows = []
for g, c in coh.groupby('game'):
    t = mn.arm_table(c, 'autoclip_holdout', ['post14_manual_clips', 'post14_shares', 'retained_d14_27', 'post14_deletes'], treat=0)
    for y, r in t.iterrows():
        rows.append(dict(game=g, outcome=y, rel_effect=r.rel, lo=r.lo / r.mean_holdout if r.mean_holdout else np.nan, hi=r.hi / r.mean_holdout if r.mean_holdout else np.nan))
PRIOR = pd.DataFrame(rows); print(PRIOR.round(3).to_string(index=False))
print('\nUse these as the priors for the MDE choice: shares/player moved +25–110% (easy to detect), retention a few pp (needs the full horizon), manual clips −11% on RL (the guardrail is live).')"""))

C.append(md("## 5 · Close — the brief in five lines"))
C.append(code(r"""d_rl = DUR[(DUR.game == 'Rocket League') & (DUR.holdout_share == 0.2)].horizon_weeks.iloc[0]; d_gj = DUR[(DUR.game == 'Ghost Janitors') & (DUR.holdout_share == 0.2)].horizon_weeks.iloc[0]
display(Markdown(mn.close_md('Next integration — experiment brief',
    f"Default-on vs off, randomized at the player (solo) or party (co-op) level, 20% control, primary = players with a kept-or-shared clip in 14 days, horizon {d_rl} weeks (accrual + 4 weeks of outcome maturation) for an RL-sized game and {d_gj} weeks for a GJ-sized co-op game to detect 3 pp on retention.",
    'GO with the 20% control; a 5% holdout cannot detect anything we care about on a small game and should be refused.',
    'pre-register the brief; log client version, flag state and party id from day 0; CUPED on the 28-day pre metric; one interim look.',
    'hotkey clips per session −10% or deletions per player +100% vs control at any look → pause and prune triggers before continuing.',
    'at the horizon: ship, extend, or stop; then size the studio funnel with the share counts from the treated arm.')))"""))

C.append(md("""## 6 · Limits
- ICC within parties is assumed, not measured; the dotted lines bracket it. Logging party ids is the fix.
- New players and existing players have different base rates; the grid uses existing players. Run the two strata separately.
- The MDE grid assumes the platform-scale population (×40); if the next game is smaller, read the small-game column.
- Opt-in arms measure uptake × effect; do not compare them with default-on on the same metric without the compliance adjustment."""))

if __name__ == "__main__":
    for c in C:
        if c.cell_type == "code":
            c.source = c.source.replace("__NBDIR__", str(NB))
    OUT.mkdir(parents=True, exist_ok=True)
    build_and_execute(nb, str(OUT / "07_experiment_design.ipynb"), workdir=str(OUT))
