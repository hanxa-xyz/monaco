"""Notebook 03 — the control-games answer: difference-in-differences and event study.

Four games had no auto-clip launch in the window (Marvel Rivals, Phasmophobia, Lethal Company; Valorant was always on). They
carry the seasonality, summer and platform drift that the pre/post projection in notebook 01 cannot separate from the launch.
Same questions, third identification: DiD on the game × week panel for Medal metrics, DiD on the studio feeds (Ghost Janitors
vs Lethal Company) for wishlists and copies, a placebo on an untreated game, and the time-to-delete curves by trigger class.

    python3 datasets/medal/nb/build_03_did_controls.py   ->  datasets/medal/out/notebooks/03_did_controls.ipynb
"""
from pathlib import Path

from monaco.viz import build_and_execute, code, md, new_notebook

NB = Path(__file__).resolve().parent
OUT = NB.parent / "out" / "notebooks"
nb = new_notebook(); C = nb.cells

C.append(md("""# Medal auto-clipping — 03 · the control-games answer (difference-in-differences)

**Same objective** (data volume · engagement · outcomes for the game), **third identification**: games that did not launch
auto-clipping in the window are the counterfactual for the ones that did. The estimate is
`ATT = (treated post − treated pre) − (control post − control pre)` on a game × week panel, with the event study as the
evidence for parallel pre-trends. For the studio question, Ghost Janitors is compared with Lethal Company (paid, Steam, same
Summer Sale) on wishlists and copies per DAU.

**Can say:** the launch effect net of anything that moved all games together (summer, platform changes, seasonality).
**Cannot say:** anything about shocks specific to one game in the post window (an RLCS Major, a launch-week discount); those stay
in the estimate and are flagged, not removed. Units are games, so the SE comes from a handful of clusters: treat CIs as floors.

Panel: `game_weekly_panel` (one row = game × ISO week), `studio_daily` aggregated to weeks, `clips` for time-to-delete."""))

C.append(md("## 0 · Setup and the panel"))
C.append(code(r"""import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0, '__NBDIR__')
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from IPython.display import Markdown, display
import medal_nb as mn
from monaco import causal as cz, survival as sv
mn.setup()
T = mn.load('game_weekly_panel', 'games', 'studio_daily', 'clips', 'game_daily')
W = T['game_weekly_panel'].copy(); W['game'] = W.game_id.map(mn.NAME)
W = W[W.week < W.week.max()]                      # last week is partial
W['wk'] = ((W.week - W.week.min()).dt.days // 7).astype(int)
print('one row = game × week;', len(W), 'rows,', W.game.nunique(), 'games,', W.wk.nunique(), 'weeks', W.week.min().date(), '→', W.week.max().date())
print(W.groupby('game').agg(weeks=('wk', 'nunique'), player_days=('player_days', 'sum'), manual=('clips_manual', 'sum'), auto=('clips_auto', 'sum')).to_string())
CONTROLS = ['Marvel Rivals', 'Phasmophobia', 'Lethal Company']
print('\ncontrols:', CONTROLS, '· Valorant is excluded (auto-clipping live since 2025-09, always treated)')"""))

C.append(md("## 1 · Do the controls track the treated games before launch? (each game indexed to its own pre-launch mean)"))
C.append(code(r"""fig, axes = plt.subplots(1, 2, figsize=(13, 4.2), sharey=True)
for ax, m in zip(axes, ('manual_per_player_day', 'shares_per_player_day')):
    for g, s in W.groupby('game'):
        base = s[s.week < mn.LAUNCH[1]][m].mean()
        col = {'Rocket League': mn.BLACK, 'Ghost Janitors': mn.O_DARK, 'Valorant': mn.O_LIGHT}.get(g, mn.GRAY)
        ax.plot(s.week, s[m] / base, color=col, lw=2 if g in ('Rocket League', 'Ghost Janitors') else 1.2, label=g, alpha=1 if col != mn.GRAY else .8)
    ax.axvline(mn.LAUNCH[1], color=mn.BLACK, ls='--', lw=1); ax.axvline(mn.LAUNCH[2], color=mn.O_DARK, ls='--', lw=1); ax.axhline(1, color=mn.GRAY, lw=.8)
    ax.set_title(m.replace('_', ' ') + ' (index, pre-RL-launch mean = 1)', loc='left', fontsize=9.5, fontweight='bold')
axes[0].legend(fontsize=8, ncol=2)
fig.suptitle('Treated games (black, dark orange) vs never-treated controls (grey): parallel before the dashed lines is the assumption', x=0.01, ha='left', fontweight='bold')
fig.tight_layout(rect=(0, 0, 1, 0.93)); plt.show()
pre = W[W.week < mn.LAUNCH[1]].groupby('game')[['manual_per_player_day', 'shares_per_player_day', 'share_per_clip']].mean().round(3)
print('pre-launch levels (RL launch as the cut):'); print(pre.to_string())"""))

C.append(md("## 2 · DiD on the Medal metrics: each treated game vs the never-treated controls"))
C.append(code(r"""def did_game(treated, ys, drop_games=()):
    L = mn.LAUNCH[1 if treated == 'Rocket League' else 2]
    Lw = L - pd.Timedelta(days=L.dayofweek)
    P = W[W.game.isin([treated] + CONTROLS) & ~W.game.isin(drop_games)].copy()
    P['treated'] = (P.game == treated).astype(int); P['post'] = (P.week >= Lw).astype(int)
    P = P[(P.week < Lw) | (P.week >= Lw + pd.Timedelta(days=mn.RAMP))]            # skip the client ramp weeks
    rows, R = [], {}
    for y in ys:
        r = cz.did(P, 'game', 'week', y, 'treated', 'post', n_boot=400); R[y] = (P, r)
        rows.append(dict(game=treated, outcome=y, treated_pre=r['cells'].loc['treated', 'pre'], att=r['att'], se=r['se'], lo=r['lo'], hi=r['hi'], p=r['p'],
                         rel=r['att'] / r['cells'].loc['treated', 'pre'], rel_lo=r['lo'] / r['cells'].loc['treated', 'pre'], rel_hi=r['hi'] / r['cells'].loc['treated', 'pre'],
                         n_control_units=r['n_control_units']))
    return pd.DataFrame(rows).set_index(['game', 'outcome']), R
YS = ['manual_per_player_day', 'shares_per_player_day', 'share_per_clip']
DID = {}; tabs = []
for g in ('Rocket League', 'Ghost Janitors'):
    tab, R = did_game(g, YS); DID[g] = R; tabs.append(tab)
DIDT = pd.concat(tabs)
print(DIDT.round(4).to_string())
print('\n[caveat printed by the estimator] one treated unit: the bootstrap resamples controls only → the CI is a floor; the event study carries the parallel-trends evidence.')
for g in ('Rocket League', 'Ghost Janitors'):
    P, r = DID[g]['manual_per_player_day']
    fig, note = cz.plot_did(P, 'week', 'manual_per_player_day', 'treated', mn.LAUNCH[1 if g == 'Rocket League' else 2], r, y_label='manual (hotkey) clips per player-day', fmt=lambda v: f'{v:+.3f}')
    fig.axes[0].set_title(f'{g}: manual clips per player-day, DiD vs {len(CONTROLS)} control games', loc='left', fontsize=10.8, fontweight='bold', pad=22)
    plt.show(); print(note)"""))

C.append(md("## 3 · Event study: the pre-trend test and the dynamic effect (weeks relative to launch)"))
C.append(code(r"""ES = {}
for g in ('Rocket League', 'Ghost Janitors'):
    P, _ = DID[g]['manual_per_player_day']
    L = mn.LAUNCH[1 if g == 'Rocket League' else 2]; Lw = L - pd.Timedelta(days=L.dayofweek)
    P2 = W[W.game.isin([g] + CONTROLS)].copy(); P2['treated'] = (P2.game == g).astype(int)
    t0 = int(P2.loc[P2.week == Lw, 'wk'].iloc[0])
    try:
        es, pre = cz.event_study(P2, 'game', 'wk', 'manual_per_player_day', 'treated', t0, window=(-8, 10), n_boot=300)   # integer week index: works around the date bug in cli_did
        ES[g] = (es, pre)
        print(f'\n== {g}: event study on manual clips per player-day (reference = week −1)')
        print(es.round(4).to_string())
        print(f"pre-trend joint test: chi2 = {pre['chi2']:.2f}, df = {pre['df']}, p = {pre['p']:.2f}; max |pre coef| = {pre['max_abs_pre']:.4f} vs ATT {DIDT.loc[(g, 'manual_per_player_day'), 'att']:+.4f}")
        fig, note = cz.plot_event_study(es, pre, y_label='manual clips per player-day vs control'); fig.axes[0].set_title(f'{g}: event study', loc='left', fontsize=10.8, fontweight='bold', pad=22); plt.show(); print(note)
    except Exception as ex:
        print(f'{g}: event study failed → {type(ex).__name__}: {ex}')
print('\nRead: weeks 0–1 are the client ramp (partial treatment); the level from week 2 on is the effect. Pre coefficients on zero = the controls are a fair counterfactual.')"""))

C.append(md("## 4 · Placebo: pretend an untreated game launched on May 7"))
C.append(code(r"""rows = []
for fake in CONTROLS:
    others = [c for c in CONTROLS if c != fake]
    Lw = mn.LAUNCH[1] - pd.Timedelta(days=mn.LAUNCH[1].dayofweek)
    P = W[W.game.isin([fake] + others)].copy(); P['treated'] = (P.game == fake).astype(int); P['post'] = (P.week >= Lw).astype(int)
    for y in ('manual_per_player_day', 'shares_per_player_day'):
        r = cz.did(P, 'game', 'week', y, 'treated', 'post', n_boot=300)
        rows.append(dict(fake_treated=fake, outcome=y, att=r['att'], lo=r['lo'], hi=r['hi'], rel=r['att'] / r['cells'].loc['treated', 'pre']))
PL = pd.DataFrame(rows)
print(PL.round(4).to_string(index=False))
print('\nA placebo ATT of the same size as the real one would mean the design cannot tell launch from noise. Compare |rel| here with the treated rows in section 2.')"""))

C.append(md("## 5 · The studio question with a control: Ghost Janitors vs Lethal Company on wishlists and copies per DAU"))
C.append(code(r"""E = T['studio_daily'].drop_duplicates(['game_id', 'date']).copy(); E['game'] = E.game_id.map(mn.NAME)
E['week'] = E.date - pd.to_timedelta(E.date.dt.dayofweek, unit='D')
E['sale'] = False
for gid, s in E.groupby('game_id'):
    sp = mn.spikes(s.set_index('date').copies_sold, window=31, ratio=1.8); E.loc[s.index, 'sale'] = sp.values
EW = E.groupby(['game', 'week']).agg(dau=('dau', 'mean'), wishlists=('wishlists', 'sum'), copies=('copies_sold', 'sum'), sale_days=('sale', 'sum')).reset_index()
EW['wishlists_per_dau'] = EW.wishlists / EW.dau / 7; EW['copies_per_dau'] = EW.copies / EW.dau / 7
L = mn.LAUNCH[2]; Lw = L - pd.Timedelta(days=L.dayofweek)
EW['treated'] = (EW.game == 'Ghost Janitors').astype(int); EW['post'] = (EW.week >= Lw).astype(int)
EW = EW[EW.week < EW.week.max()]
print('weeks with sale-like copy spikes (dropped from the estimate):'); print(EW[EW.sale_days > 0][['game', 'week', 'sale_days']].assign(week=lambda x: x.week.dt.date).to_string(index=False))
clean = EW[EW.sale_days == 0]
fig, axes = plt.subplots(1, 3, figsize=(14, 3.8))
for ax, m in zip(axes, ('dau', 'wishlists_per_dau', 'copies_per_dau')):
    for g, s in EW.groupby('game'):
        base = s[s.week < Lw][m].mean(); ax.plot(s.week, s[m] / base, color=mn.BLACK if g == 'Ghost Janitors' else mn.O_MID, lw=1.8, label=g)
        ax.scatter(s[s.sale_days > 0].week, s[s.sale_days > 0][m] / base, color=mn.O_DARK, s=28, zorder=3)
    ax.axvline(L, color=mn.GRAY, ls='--', lw=1); ax.axhline(1, color=mn.GRAY, lw=.8); ax.set_title(f'{m} (index, pre = 1)', loc='left', fontsize=9.5, fontweight='bold')
axes[0].legend(fontsize=8)
fig.suptitle('Ghost Janitors vs Lethal Company: both paid Steam co-op games, same Summer Sale · dots = sale-spike weeks (excluded)', x=0.01, ha='left', fontweight='bold')
fig.tight_layout(rect=(0, 0, 1, 0.92)); plt.show()
# one treated unit vs one control unit: the cluster bootstrap has nothing to resample, so the SE comes from the WEEKLY treated − control
# differences (pre weeks vs post weeks treated as independent draws). Weeks are the clusters here; say so.
rows = []
for m in ('wishlists_per_dau', 'copies_per_dau', 'dau'):
    wide = clean.pivot(index='week', columns='game', values=m).dropna()
    diff = wide['Ghost Janitors'] - wide['Lethal Company']
    pre_d, post_d = diff[diff.index < Lw], diff[diff.index >= Lw + pd.Timedelta(days=mn.RAMP)]
    att = post_d.mean() - pre_d.mean(); se = np.sqrt(post_d.var(ddof=1) / len(post_d) + pre_d.var(ddof=1) / len(pre_d))
    gj_pre = wide.loc[wide.index < Lw, 'Ghost Janitors'].mean()
    rows.append(dict(outcome=m, gj_pre=gj_pre, att=att, se=se, lo=att - 1.96 * se, hi=att + 1.96 * se, rel=att / gj_pre, rel_lo=(att - 1.96 * se) / gj_pre, rel_hi=(att + 1.96 * se) / gj_pre,
                     n_pre_weeks=len(pre_d), n_post_weeks=len(post_d)))
STU = pd.DataFrame(rows).set_index('outcome')
print(STU.round(4).to_string())
print('(cz.did on the same panel gives the identical point estimate; its bootstrap CI collapses with one unit per arm, so it is not shown)')
# what the DiD lift implies per auto-clip share, against the reach ceiling
gd = mn.derive_daily(T['game_daily'], 2); post_d = gd[(gd.index >= L + mn.D(mn.RAMP))]
cl = T['clips'].drop_duplicates('clip_id'); gj_auto = cl[(cl.game_id == 2) & (cl.trigger_class == 'autoclip_native') & cl.shared_14d.notna()]
share_rate = gj_auto.shared_14d.mean(); auto_shares_day = post_d.clips_autoclip_native.mean() * share_rate
dau_post = EW[(EW.game == 'Ghost Janitors') & (EW.post == 1)].dau.mean()
for m, lbl in (('wishlists_per_dau', 'wishlists'), ('copies_per_dau', 'copies')):
    per_day = STU.loc[m, 'att'] * dau_post
    print(f"{lbl}: DiD {STU.loc[m, 'rel']:+.1%} (CI {STU.loc[m, 'rel_lo']:+.0%}…{STU.loc[m, 'rel_hi']:+.0%}) ≈ {per_day:+.1f}/day on ~{dau_post:,.0f} DAU; auto-clip shares ≈ {auto_shares_day:.1f}/day → implied {per_day / auto_shares_day:+.2f} {lbl} per share (ceiling: 2 wishlists / 0.5 copies)")
print('\nThe launch-week discount (May 21–27) is a GJ-only shock inside the post window: it is dropped as a sale spike, but the DAU it brought persists in the per-DAU denominators. Say so.')"""))

C.append(md("## 6 · Time-to-delete by trigger class (Kaplan-Meier, censoring handled) — the quality question with its clock"))
C.append(code(r"""samp = cl[cl.game_id.isin([1, 2])].sample(20000, random_state=7)     # km() is O(distinct event times); 20k rows run in seconds, 125k take minutes
samp['cls'] = samp.game_id.map(mn.NAME) + ' · ' + samp.trigger_class.str.replace('autoclip_', '')
d = sv.from_timestamps(samp, 'captured_ts', 'deleted_ts', as_of=mn.AS_OF, group='cls', unit='D')
d['duration'] = np.floor(d.duration)
print(d.attrs['note'])
curves = {}
for g, dg in d.groupby('group'):
    curves[g] = sv.km(dg.duration, dg.event)
rows = []
for g, tab in curves.items():
    s = sv.survival_at(tab, [1, 7, 14, 30]); rows.append(dict(group=g, n=int((d.group == g).sum()), **{f'S_{int(t)}': v for t, v in zip(s.t, s.S)}, rmst_30=sv.rmst(tab, 30)))
KM = pd.DataFrame(rows).set_index('group'); print(KM.round(3).to_string())
chi2, dfree, pval, _ = sv.logrank(d)
print(f"log-rank across groups: chi2 = {chi2:,.1f}, df = {dfree}, p = {pval:.2g} — curves differ; association, not effect (clips self-select into classes)")
order = ['Rocket League · hotkey', 'Rocket League · native', 'Ghost Janitors · hotkey', 'Ghost Janitors · native']
fig, note = sv.plot_km({k: curves[k] for k in order if k in curves}, [1, 7, 14, 30], 'days', title='Clip survival: time from capture to deletion',
                       subtitle='20k-clip sample · black = RL hotkey · censored at 2026-09-01 · steps = deletions', xmax=45, show_at_risk=False)
plt.show(); print(note)
print('\nRead: 1 − S(14) is the 14-day delete rate with censoring done properly; the gap between hotkey and native curves is the curation cost of auto-clips, and it is set in the first 2 days.')"""))

C.append(md("## 7 · Close — from the control-game contrasts"))
C.append(code(r"""def pct(x): return 'n/a' if pd.isna(x) else f'{x:+.0%}'
for g in ('Rocket League', 'Ghost Janitors'):
    man = DIDT.loc[(g, 'manual_per_player_day')]; sh = DIDT.loc[(g, 'shares_per_player_day')]; spc = DIDT.loc[(g, 'share_per_clip')]
    pre_ok = ES.get(g, (None, {'p': np.nan}))[1]['p']
    head = (f"vs {len(CONTROLS)} never-treated games: manual clips per player-day {pct(man.rel)} (CI {man.rel_lo:+.0%}…{man.rel_hi:+.0%}), shares per player-day {pct(sh.rel)} "
            f"(CI {sh.rel_lo:+.0%}…{sh.rel_hi:+.0%}), shares per clip {pct(spc.rel)}; pre-trend test p = {pre_ok:.2f}.")
    if g == 'Ghost Janitors':
        head += (f" Studio vs Lethal Company: wishlists per DAU {pct(STU.loc['wishlists_per_dau', 'rel'])} (CI {STU.loc['wishlists_per_dau', 'rel_lo']:+.0%}…{STU.loc['wishlists_per_dau', 'rel_hi']:+.0%}), "
                 f"copies per DAU {pct(STU.loc['copies_per_dau', 'rel'])} (CI {STU.loc['copies_per_dau', 'rel_lo']:+.0%}…{STU.loc['copies_per_dau', 'rel_hi']:+.0%}).")
    cannibal = man.rel_hi < 0
    go = ('GO; cannibalization confirmed against controls — price it' if cannibal else 'GO; no cannibalization against controls') + (' and engagement per player up' if sh.rel_lo > 0 else '')
    if g == 'Ghost Janitors':
        go += '; studio lift is ' + ('positive against a paid control — a case study with one control is still one control' if STU.loc['wishlists_per_dau', 'rel_lo'] > 0 else 'not distinguishable from the control')
    action = 'ship the pruned trigger set platform-wide; for the next studio integration, hold out a matched paid game as the control from day 0 and log the discount calendar.'
    guard = f"treated-minus-control manual clips per player-day below {man.treated_pre * 0.85:.3f} (−15%) for two weeks; shares per player-day treated-minus-control turning negative."
    revisit = 'at week 12 post-launch with the same panel (the Summer Sale weeks will have dropped out), and with Valorant added back as an always-treated comparison for the level.'
    display(Markdown(mn.close_md(g, head, go, action, guard, revisit)))"""))

C.append(md("""## 8 · Limits of this approach
- One treated game per estimate and three controls: the bootstrap CI reflects control noise only. The event study and the placebo are the real evidence.
- Game-specific shocks in the window (RLCS Major for RL; launch discount and a June patch for GJ) are inside the ATT. Dropping sale-spike weeks removes the days, not the players they brought.
- Controls were not chosen for similarity on mechanics; a synthetic-control weighting of a larger donor pool (the 13 platform games, if their daily data existed) is the upgrade.
- Across the three notebooks the answers agree in sign; where they disagree in size, trust 02 (randomized) over 03 (controls) over 01 (projection)."""))

if __name__ == "__main__":
    for c in C:
        if c.cell_type == "code":
            c.source = c.source.replace("__NBDIR__", str(NB))
    OUT.mkdir(parents=True, exist_ok=True)
    build_and_execute(nb, str(OUT / "03_did_controls.ipynb"), workdir=str(OUT))
