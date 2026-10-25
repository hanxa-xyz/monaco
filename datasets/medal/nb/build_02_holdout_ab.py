"""Notebook 02 — the randomized-holdout answer.

20% of each launched game's Medal players never received auto-clips (players.autoclip_holdout = 1). The pre-launch-active
cohort (player_launch_cohort) is the A/B table: balance on pre-period covariates, intention-to-treat effects with intervals,
CUPED variance reduction, the selection trap made visible (got-an-auto-clip vs holdout), treatment-vs-control over time from
the session rows, heterogeneity, trigger quality with intervals, and the power table for the next rollout.

    python3 datasets/medal/nb/build_02_holdout_ab.py   ->  datasets/medal/out/notebooks/02_holdout_ab.ipynb
"""
from pathlib import Path

from monaco.viz import build_and_execute, code, md, new_notebook

NB = Path(__file__).resolve().parent
OUT = NB.parent / "out" / "notebooks"
nb = new_notebook(); C = nb.cells

C.append(md("""# Medal auto-clipping — 02 · the randomized-holdout answer

**Same objective** as notebook 01 (data volume · on-platform engagement · outcomes for the game), **different identification**:
at each launch 20% of the game's Medal players were held out (`autoclip_holdout = 1`, never receive auto-clips). Randomization
makes the holdout the counterfactual, so every contrast here is an **intention-to-treat effect**, not a before/after.

Unit = a player who was active in the 28 days before launch (`player_launch_cohort`). Outcomes are measured in the first 14
days after launch and retention in days 14–27 and 28–41. Pre-period covariates (sessions, manual clips, shares in the 28
days before) serve two purposes: a balance check, and CUPED variance reduction.

**Can say:** the causal effect of being offered auto-clipping on this cohort. **Cannot say:** anything about players who joined
after launch, or spillovers between party members (a holdout player in a co-op lobby still sees friends' clips)."""))

C.append(md("## 0 · Setup"))
C.append(code(r"""import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0, '__NBDIR__')
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from IPython.display import Markdown, display
import medal_nb as mn
from monaco import causal as cz
mn.setup()
T = mn.load('player_launch_cohort', 'sessions', 'players', 'clips', 'games')
coh = T['player_launch_cohort']; coh['game'] = coh.game_id.map(mn.NAME)
print(coh.groupby(['game', 'autoclip_holdout']).size().unstack().rename(columns={0: 'auto-on', 1: 'holdout'}))
print('\none row =', 'a (player, game) active in the 28 days before that game\'s launch; holdout share by construction 20%')"""))

C.append(md("## 1 · Balance: did randomization work? (pre-period covariates by arm)"))
C.append(code(r"""COV = ['pre28_sessions', 'pre28_minutes', 'pre28_manual_clips', 'pre28_shares', 'tenure_days_at_launch', 'premium', 'steam_linked']
rows = []
for g, c in coh.groupby('game'):
    for v in COV:
        a, b = c.loc[c.autoclip_holdout == 0, v], c.loc[c.autoclip_holdout == 1, v]
        rows.append(dict(game=g, covariate=v, mean_on=a.mean(), mean_holdout=b.mean(), smd=cz.smd(c[v].values, (c.autoclip_holdout == 0).astype(int).values)))
bal = pd.DataFrame(rows)
print(bal.round(3).to_string(index=False))
print('\n|SMD| < 0.1 on every covariate = balanced; a heavy-tailed covariate (manual clips) can still sit at 0.1–0.2 by chance — that is what CUPED is for.')"""))

C.append(md("## 2 · Intention-to-treat effects: auto-on vs holdout, first 14 days and retention"))
C.append(code(r"""OUTC = ['post14_sessions', 'post14_clips_total', 'post14_manual_clips', 'post14_shares', 'post14_deletes', 'retained_d14_27', 'retained_d28_41']
ITT = {}
for g, c in coh.groupby('game'):
    tab = mn.arm_table(c, 'autoclip_holdout', OUTC, treat=0); ITT[g] = tab
    print(f'\n== {g}  (auto-on n={tab.n_on.iloc[0]:,}, holdout n={tab.n_holdout.iloc[0]:,})')
    print(tab[['mean_on', 'mean_holdout', 'diff', 'lo', 'hi', 'rel', 'p']].round(3).to_string())
    mn.plot_arms(tab, f'{g}: effect of being offered auto-clipping (ITT), relative to holdout',
                 'first 14 days after launch; retention = any session in the window · whiskers 95% CI · orange = CI excludes 0'); plt.show()
print('\nRead: clips_total is mechanical (auto-clips are inside it). The three numbers that matter: manual clips (cannibalization), shares (engagement), retention (the studio question).')"""))

C.append(md("## 3 · CUPED: the same effects with the pre-period noise removed"))
C.append(code(r"""PAIRS = [('retained_d14_27', 'pre28_sessions'), ('post14_sessions', 'pre28_sessions'), ('post14_manual_clips', 'pre28_manual_clips'), ('post14_shares', 'pre28_shares')]
rows = []
for g, c in coh.groupby('game'):
    for y, ypre in PAIRS:
        tab, info = cz.cuped(c, y, ypre, 'autoclip_holdout', treatment_label=0)
        rows.append(dict(game=g, outcome=y, covariate=ypre, naive_diff=tab.loc['naive', 'diff'], naive_se=tab.loc['naive', 'se'],
                         cuped_diff=tab.loc['cuped', 'diff'], cuped_se=tab.loc['cuped', 'se'], cuped_lo=tab.loc['cuped', 'lo'], cuped_hi=tab.loc['cuped', 'hi'],
                         theta=info['theta'], corr_pre=info['corr'], var_reduction=info['variance_reduction']))
CU = pd.DataFrame(rows)
print(CU.round(4).to_string(index=False))
print('\nCUPED shrinks the SE by the pre-period correlation squared; it does not change what is being estimated. Quote the CUPED row when the naive one straddles zero because of a pre-period imbalance.')"""))

C.append(md("## 4 · The selection trap, made visible: 'got an auto-clip' vs 'was offered auto-clipping'"))
C.append(code(r"""rows = []
for g, c in coh.groupby('game'):
    on = c[c.autoclip_holdout == 0]
    naive = on.groupby('got_autoclip_14d').retained_d14_27.mean()
    itt = ITT[g].loc['retained_d14_27']
    rows.append(dict(game=g, naive_got_vs_not_pp=(naive.get(1, np.nan) - naive.get(0, np.nan)) * 100, n_got=int((on.got_autoclip_14d == 1).sum()), n_not=int((on.got_autoclip_14d == 0).sum()),
                     itt_on_vs_holdout_pp=itt['diff'] * 100, itt_lo_pp=itt.lo * 100, itt_hi_pp=itt.hi * 100))
SEL = pd.DataFrame(rows).set_index('game')
print(SEL.round(1).to_string())
fig, ax = plt.subplots(figsize=(8, 3.2))
y = np.arange(len(SEL))
ax.barh(y + 0.2, SEL.naive_got_vs_not_pp, height=0.38, color=mn.O_PALE, label='naive: got an auto-clip vs did not (selection)')
ax.barh(y - 0.2, SEL.itt_on_vs_holdout_pp, height=0.38, color=mn.BLACK, label='ITT: offered vs holdout (randomized)')
ax.errorbar(SEL.itt_on_vs_holdout_pp, y - 0.2, xerr=[SEL.itt_on_vs_holdout_pp - SEL.itt_lo_pp, SEL.itt_hi_pp - SEL.itt_on_vs_holdout_pp], fmt='none', ecolor=mn.O_DARK, capsize=2)
for yy, a, b in zip(y, SEL.naive_got_vs_not_pp, SEL.itt_on_vs_holdout_pp):
    ax.text(a, yy + 0.2, f' {a:+.1f} pp', va='center', fontsize=8); ax.text(max(b, 0), yy - 0.2, f' {b:+.1f} pp', va='center', fontsize=8)
ax.set_yticks(y, SEL.index); ax.axvline(0, color=mn.GRAY, lw=1); ax.legend(fontsize=8, loc='lower right'); ax.grid(axis='x')
mn.titled(ax, 'Retention d14–27: the naive gap is selection, the randomized gap is the effect', 'players who got a clip played more that fortnight — they would have returned anyway')
plt.show()"""))

C.append(md("## 5 · Treatment vs control over time (from the session rows): hotkey clips and shares per session, by arm"))
C.append(code(r"""S = T['sessions'].merge(T['players'][['player_id', 'autoclip_holdout']], on='player_id', how='inner')
cl = T['clips'].drop_duplicates('clip_id')
per_s = cl.groupby('session_id').agg(hotkey=('trigger_class', lambda x: (x == 'hotkey').sum()), shares=('shared_ts', lambda x: x.notna().sum()), auto=('trigger_class', lambda x: (x != 'hotkey').sum()))
S = S.join(per_s, on='session_id').fillna({'hotkey': 0, 'shares': 0, 'auto': 0})
S['week'] = S.session_date - pd.to_timedelta(S.session_date.dt.dayofweek, unit='D')
S = S[S.week < S.week.max()]                      # last ISO week is partial (one day)
fig, axes = plt.subplots(2, 2, figsize=(12, 6.5), sharex=True)
WK, DIDS = {}, {}
for j, gid in enumerate((1, 2)):
    s = S[S.game_id == gid]; L = mn.LAUNCH[gid]
    w = s.groupby(['week', 'autoclip_holdout']).agg(sessions=('session_id', 'size'), hotkey=('hotkey', 'sum'), shares=('shares', 'sum'), players=('player_id', 'nunique'))
    w['hotkey_per_session'] = w.hotkey / w.sessions; w['shares_per_session'] = w.shares / w.sessions
    WK[gid] = w
    for i, m in enumerate(('hotkey_per_session', 'shares_per_session')):
        ax = axes[i, j]; u = w[m].unstack()
        ax.plot(u.index, u[0], color=mn.BLACK, lw=1.8, label='auto-on arm'); ax.plot(u.index, u[1], color=mn.O_MID, lw=1.8, label='holdout arm')
        ax.axvline(L, color=mn.GRAY, ls='--', lw=1); ax.set_title(f'{mn.NAME[gid]}: {m.replace("_", " ")}', loc='left', fontsize=9.5, fontweight='bold')
        if i == 0 and j == 0: ax.legend(fontsize=8)
fig.suptitle('Both arms move together before launch and split after it — that is the whole case for a holdout', x=0.01, ha='left', fontweight='bold')
fig.tight_layout(rect=(0, 0, 1, 0.95)); plt.show()
for gid in (1, 2):
    w = WK[gid]; L = mn.LAUNCH[gid]
    pre = w[w.index.get_level_values('week') < L].groupby('autoclip_holdout').hotkey_per_session.mean()
    post = w[w.index.get_level_values('week') >= L + mn.D(mn.RAMP)].groupby('autoclip_holdout').hotkey_per_session.mean()
    did = (post[0] / pre[0]) / (post[1] / pre[1]) - 1
    DIDS[mn.NAME[gid]] = did
    print(f"{mn.NAME[gid]}: hotkey clips/session pre on {pre[0]:.3f} vs holdout {pre[1]:.3f}; post on {post[0]:.3f} vs holdout {post[1]:.3f} → DiD {did:+.1%} (the cannibalization number, pre-imbalance removed)")"""))

C.append(md("## 6 · Heterogeneity: who responds? (pre-launch activity terciles)"))
C.append(code(r"""rows = []
for g, c in coh.groupby('game'):
    c = c.copy(); c['activity'] = pd.qcut(c.pre28_sessions.rank(method='first'), 3, labels=['light', 'mid', 'heavy'])
    for tier, ct in c.groupby('activity'):
        t = mn.arm_table(ct, 'autoclip_holdout', ['retained_d14_27', 'post14_shares', 'post14_manual_clips'], treat=0)
        for y, r in t.iterrows():
            rows.append(dict(game=g, tier=tier, outcome=y, n_on=r.n_on, n_holdout=r.n_holdout, diff=r['diff'], lo=r.lo, hi=r.hi, rel=r.rel))
HET = pd.DataFrame(rows)
print(HET.round(3).to_string(index=False))
print('\nTerciles of 100–400 players each: read direction, not decimals. A consistent sign across tiers is the finding; a sign flip is a hypothesis for the next test.')"""))

C.append(md("## 7 · Clip quality from the rows: 14-day outcomes per trigger with intervals, and the prune set"))
C.append(code(r"""post_clips = cl[(cl.game_id.isin([1, 2])) & cl.deleted_14d.notna() & (cl.trigger_class != 'hotkey')].copy()
post_clips = post_clips[post_clips.captured_ts >= post_clips.game_id.map(mn.LAUNCH)]
post_clips['trigger_name'] = post_clips.trigger_name.fillna('(unknown)').str.title()
for gid in (1, 2):
    c = post_clips[post_clips.game_id == gid]
    t = mn.rate_table(c, 'trigger_name', ['shared_14d', 'deleted_14d'])
    ref = c.shared_14d.mean()
    print(f'\n== {mn.NAME[gid]} (post-launch auto-clips with a full 14 days)'); print(t.round(3).to_string())
    mn.barh_rates(t, 'shared_14d', f'{mn.NAME[gid]}: share rate per trigger (row level)', 'Wilson 95% · pale = n < 30 · note the "(unknown)" and casing warts', ref=ref); plt.show()
hot = cl[(cl.game_id.isin([1, 2])) & cl.deleted_14d.notna()].groupby(['game_id', 'trigger_class'])[['deleted_14d', 'shared_14d']].mean().round(3)
print('\nby trigger class, all weeks with a full 14 days:'); print(hot.to_string())"""))

C.append(md("## 8 · Power for the next rollout: what holdout size detects what"))
C.append(code(r"""SCALE = 40   # the row-level sample is ~1/40 of each game's Medal population
rows = []
for g, c in coh.groupby('game'):
    p0 = c.loc[c.autoclip_holdout == 1, 'retained_d14_27'].mean(); n = len(c) * SCALE
    t = mn.mde_table(p0, [int(n * 0.5), int(n * 0.8), int(n * 0.95)], [0.5, 0.2, 0.05])
    t.insert(0, 'game', g); t.insert(1, 'base_retention', round(p0, 3)); rows.append(t)
MDE = pd.concat(rows)
print(MDE.round(2).to_string(index=False))
print('\nRead: a 5% holdout on Ghost Janitors cannot see a 3 pp retention effect in 14 days; a 20% holdout can. Unit of randomization for a co-op game should be the party or the lobby, not the player (spillover).')"""))

C.append(md("## 9 · Close — from the randomized contrasts"))
C.append(code(r"""def pct(x): return 'n/a' if pd.isna(x) else f'{x:+.0%}'
for g in ('Rocket League', 'Ghost Janitors'):
    t = ITT[g]; cu = CU[CU.game == g].set_index('outcome'); gid = 1 if g == 'Rocket League' else 2
    man, sh, ret = t.loc['post14_manual_clips'], t.loc['post14_shares'], t.loc['retained_d14_27']
    retc = cu.loc['retained_d14_27']
    head = (f"offered vs holdout: hotkey clips per session, DiD on the weekly arms {pct(DIDS[g])} (first-14-day per-player contrast {pct(man.rel)}, CI {man.lo / man.mean_holdout:+.0%}…{man.hi / man.mean_holdout:+.0%} — too short a window to read alone); shares per player {pct(sh.rel)} "
            f"(CI {sh.lo / sh.mean_holdout:+.0%}…{sh.hi / sh.mean_holdout:+.0%}); retention d14–27 {ret['diff'] * 100:+.1f} pp (CUPED {retc.cuped_diff * 100:+.1f} pp, CI {retc.cuped_lo * 100:+.1f}…{retc.cuped_hi * 100:+.1f}). "
            f"Naive got-a-clip gap {SEL.loc[g, 'naive_got_vs_not_pp']:+.0f} pp is selection.")
    ret_call = 'retention up' if retc.cuped_lo > 0 else ('retention DOWN' if retc.cuped_hi < 0 else f'retention inconclusive (CUPED CI {retc.cuped_lo * 100:+.1f}…{retc.cuped_hi * 100:+.1f} pp includes 0)')
    go = ('GO — shares per player up' if sh.lo > 0 else 'GO for volume; engagement not yet proven') + '; ' + ret_call
    go += f'; cannibalization {pct(DIDS[g])} on hotkey clips per session — ' + ('real, price it in' if DIDS[g] < -0.05 else 'not material')
    action = 'keep the holdout running until the retention CI excludes zero or 8 weeks pass; prune the junk triggers (section 7) now — that decision does not need the holdout.'
    guard = f"holdout-adjusted manual clips per player below {man.mean_holdout * 0.85:.2f} (−15%) or shares per player back to the holdout level {sh.mean_holdout:.2f}."
    revisit = 'in 4 weeks with days 28–55 retention on the same cohort; then size the studio funnel with the share counts here × the per-share rates from the external DiD (notebook 03).'
    display(Markdown(mn.close_md(g, head, go, action, guard, revisit)))"""))

C.append(md("""## 10 · Limits of this approach
- ITT on a pre-launch-active cohort: says nothing about acquisition of new players, which is where a studio case study would come from.
- Player-level randomization in a co-op game leaks: holdout players sit in lobbies with treated friends. Expect the effect to be understated.
- A 20% holdout of ~1,400 cohort players gives ±3–4 pp on retention: enough for direction, not for a pitch-deck decimal.
- The studio metrics (wishlists, copies) cannot be split by arm — they live outside Medal. That question goes to notebook 03."""))

if __name__ == "__main__":
    for c in C:
        if c.cell_type == "code":
            c.source = c.source.replace("__NBDIR__", str(NB))
    OUT.mkdir(parents=True, exist_ok=True)
    build_and_execute(nb, str(OUT / "02_holdout_ab.ipynb"), workdir=str(OUT))
