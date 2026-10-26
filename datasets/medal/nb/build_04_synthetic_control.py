"""Notebook 04 — Case 1, fourth route: synthetic control (one treated game, a donor pool of untreated games).

    python3 datasets/medal/nb/build_04_synthetic_control.py   ->  datasets/medal/out/notebooks/04_synthetic_control.ipynb
"""
from pathlib import Path

from monaco.viz import build_and_execute, code, md, new_notebook

NB = Path(__file__).resolve().parent
OUT = NB.parent / "out" / "notebooks"
nb = new_notebook(); C = nb.cells

C.append(md("""# Medal auto-clipping — 04 · synthetic control

**Same objective** (impact of auto-clipping on data volume, engagement, the game), **fourth identification**: for one treated
game, build a weighted combination of untreated games that reproduces its pre-launch path, then read the post-launch gap.
Weights are non-negative and sum to one, fit on the 56 days before launch on the 7-day-smoothed daily series, each series **indexed to its own pre-period mean** (simplex weights cannot rescale a donor, so levels are matched by indexing and the path is read in index units). Inference is by
permutation: run the same procedure with every donor as the fake treated unit and ask whether the real gap is unusual
(post/pre RMSPE ratio rank).

Donors: Marvel Rivals, Phasmophobia, Lethal Company (never treated) and Valorant (always treated → a stable level, no step).
`causal.method_ladder` lists this rung as "not implemented"; the helpers in `medal_nb.py` (`synth_control`, `placebo_in_space`)
are the implementation sketch.

**Can say:** the launch effect against a data-driven counterfactual that matches the pre-period level and seasonality.
**Cannot say:** much with four donors — the placebo distribution has four points, so the smallest achievable p is 1/5."""))

C.append(md("## 0 · Setup: the daily panel of per-player metrics"))
C.append(code(r"""import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0, '__NBDIR__')
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from IPython.display import Markdown, display
import medal_nb as mn
mn.setup()
T = mn.load('game_daily', 'games')
D_ = {gid: mn.derive_daily(T['game_daily'], gid) for gid in mn.NAME}
def wide(metric):
    return pd.DataFrame({mn.NAME[g]: d[metric] for g, d in D_.items()}).interpolate(limit=2)
DONORS = ['Marvel Rivals', 'Phasmophobia', 'Lethal Company', 'Valorant']
W = {m: wide(m) for m in ('manual_pp', 'shares_pp', 'share_per_clip', 'pct_sharing')}
print('one row = a day; one column = a game; metric = per-player daily rate')
print(W['manual_pp'].describe().round(3).to_string())"""))

C.append(md("## 1 · Fit: can the donors reproduce each treated game's pre-launch path?"))
C.append(code(r"""RES = {}
for name, gid in (('Rocket League', 1), ('Ghost Janitors', 2)):
    L = mn.LAUNCH[gid]
    for m, lbl in (('manual_pp', 'manual clips per player'), ('shares_pp', 'shares per player'), ('share_per_clip', 'shares per clip')):
        r = mn.synth_control(W[m], name, DONORS, L); RES[(name, m)] = r
        print(f"{name:<15} {m:<16} weights: " + ', '.join(f'{k} {v:.2f}' for k, v in r['weights'].items()) +
              f"  | pre RMSPE {r['rmspe_pre']:.4f}  post RMSPE {r['rmspe_post']:.4f}  ratio {r['ratio']:.1f}  → POST effect {r['effect']:+.1%}")
print('\nRead: series are indexed (pre mean = 1), so RMSPE is in relative units: 0.03 = 3% of the level. A ratio ≫ 1 means the post gap is far larger than the fit error.')"""))

C.append(md("## 2 · Rocket League and Ghost Janitors: observed vs synthetic, and the gap"))
C.append(code(r"""for name, gid in (('Rocket League', 1), ('Ghost Janitors', 2)):
    for m, lbl in (('manual_pp', 'manual clips per player'), ('shares_pp', 'shares per player')):
        mn.plot_synth(RES[(name, m)], mn.LAUNCH[gid], name, lbl); plt.show()
    r = RES[(name, 'manual_pp')]; p = r['path']; L = mn.LAUNCH[gid]
    post = p[(p.index >= L + mn.D(mn.RAMP)) & (p.index < L + mn.D(mn.RAMP + mn.POST))]
    print(f"{name}: POST manual clips/player, index units: observed {post.treated.mean():.3f} vs synthetic {post.synthetic.mean():.3f} → {r['effect']:+.1%}; "
          f"shares/player {RES[(name, 'shares_pp')]['effect']:+.1%}; shares/clip {RES[(name, 'share_per_clip')]['effect']:+.1%}")"""))

C.append(md("## 3 · Inference by permutation: in-space placebos (every donor as the fake treated unit)"))
C.append(code(r"""PL = {}
for name, gid in (('Rocket League', 1), ('Ghost Janitors', 2)):
    for m in ('manual_pp', 'shares_pp'):
        t = mn.placebo_in_space(W[m], name, DONORS, mn.LAUNCH[gid]); PL[(name, m)] = t
        rank = int(t.loc[~t.placebo, 'rank'].iloc[0]); n = len(t)
        print(f"\n== {name} · {m}: real unit ranks {rank} of {n} on post/pre RMSPE ratio → permutation p = {rank / n:.2f}")
        print(t.round(4).to_string(index=False))
fig, axes = plt.subplots(1, 2, figsize=(12, 3.6))
for ax, name in zip(axes, ('Rocket League', 'Ghost Janitors')):
    t = PL[(name, 'manual_pp')].sort_values('effect')
    ax.barh(t.unit, t.effect, color=[mn.BLACK if not p_ else mn.O_PALE for p_ in t.placebo])
    for yy, (v, p_) in enumerate(zip(t.effect, t.placebo)): ax.text(v, yy, f' {v:+.1%}', va='center', fontsize=8, color=mn.BLACK if not p_ else '#666')
    ax.axvline(0, color=mn.GRAY, lw=1); ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:+.0%}'))
    mn.titled(ax, f'{name}: POST effect on manual clips/player vs placebos', 'black = real treated unit · pale = each donor pretending to be treated')
fig.tight_layout(); plt.show()
print('\nRead: if a placebo gap is as large as the real one, the design cannot distinguish launch from donor noise. Four donors → p ≥ 0.20 even when the effect is real; say so.')"""))

C.append(md("## 4 · In-time placebo: pretend the launch happened six weeks earlier"))
C.append(code(r"""rows = []
for name, gid in (('Rocket League', 1), ('Ghost Janitors', 2)):
    fakeL = mn.LAUNCH[gid] - mn.D(42)
    for m in ('manual_pp', 'shares_pp'):
        r = mn.synth_control(W[m], name, DONORS, fakeL, fit_start=fakeL - mn.D(42))
        rows.append(dict(game=name, metric=m, fake_launch=fakeL.date(), effect_at_fake=r['effect'], real_effect=RES[(name, m)]['effect'], ratio=r['ratio']))
IT = pd.DataFrame(rows); print(IT.round(4).to_string(index=False))
print('\nA fake-launch effect near zero (and a ratio near 1) supports the real one; a large fake effect means the pre-period itself drifts and the donors do not follow it.')"""))

C.append(md("## 5 · Close"))
C.append(code(r"""def pct(x): return 'n/a' if pd.isna(x) else f'{x:+.0%}'
for name in ('Rocket League', 'Ghost Janitors'):
    r_m, r_s, r_c = RES[(name, 'manual_pp')], RES[(name, 'shares_pp')], RES[(name, 'share_per_clip')]
    pl = PL[(name, 'manual_pp')]; rank = int(pl.loc[~pl.placebo, 'rank'].iloc[0]); n = len(pl)
    worst = pl[pl.placebo].effect.abs().max()
    head = (f"synthetic control from {len(DONORS)} donors: manual clips/player {pct(r_m['effect'])} in POST (pre RMSPE {r_m['rmspe_pre']:.3f}, post/pre ratio {r_m['ratio']:.1f}, "
            f"rank {rank}/{n} among placebos → p = {rank / n:.2f}; largest placebo |effect| {worst:.1%}); shares/player {pct(r_s['effect'])}; shares/clip {pct(r_c['effect'])}.")
    cannibal = r_m['effect'] < -0.05 and abs(r_m['effect']) > worst
    go = ('GO; cannibalization visible against the synthetic path and larger than any placebo' if cannibal else 'GO; no cannibalization beyond what placebos show') + \
         ('; shares per player up' if r_s['effect'] > 0.05 else '')
    action = 'same as 03: ship the pruned trigger set; for the next launch, pre-register the donor pool and the fit window before the launch date so the weights cannot be tuned to the answer.'
    guard = "gap on manual clips/player below −15% of the synthetic path for two consecutive weeks."
    revisit = 'when the platform exports daily series for the 13 other games: a 17-donor pool makes the permutation test meaningful (p down to 1/18) and lets the weights spread.'
    display(Markdown(mn.close_md(name, head, go, action, guard, revisit)))"""))

C.append(md("""## 6 · Limits of this approach
- Four donors is a thin pool: weights concentrate on one or two games and the permutation p-value cannot go below 0.20.
- Donors carry their own events (Lethal Company patch Jul 15, Summer Sale on the paid games); a donor's shock becomes a spurious treated gap.
- Per-player rates fit well; levels (players, clips) would need donors of similar size and are not attempted.
- Agrees with 02 (holdout) and 03 (DiD) on sign and roughly on size for Rocket League; that agreement across designs is the argument, not any single CI."""))

if __name__ == "__main__":
    for c in C:
        if c.cell_type == "code":
            c.source = c.source.replace("__NBDIR__", str(NB))
    OUT.mkdir(parents=True, exist_ok=True)
    build_and_execute(nb, str(OUT / "04_synthetic_control.ipynb"), workdir=str(OUT))
