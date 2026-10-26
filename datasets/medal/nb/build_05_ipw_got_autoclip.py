"""Notebook 05 — Case 1, fifth route: selection on observables (propensity / IPW) when there is no holdout.

    python3 datasets/medal/nb/build_05_ipw_got_autoclip.py   ->  datasets/medal/out/notebooks/05_ipw_got_autoclip.ipynb
"""
from pathlib import Path

from monaco.viz import build_and_execute, code, md, new_notebook

NB = Path(__file__).resolve().parent
OUT = NB.parent / "out" / "notebooks"
nb = new_notebook(); C = nb.cells

C.append(md("""# Medal auto-clipping — 05 · propensity / IPW on "got an auto-clip"

**Same objective, fifth identification — the fallback when there is no holdout.** The packet's Return-rate table compares
players who *received* an auto-clip with those who did not. That contrast is selection: receiving a clip requires playing long
enough to trigger one. If the drivers of selection are observable (pre-launch sessions, minutes, clips, shares, tenure, premium),
inverse-probability weighting can reweight the no-clip group to look like the clip group on those covariates and read the
remaining gap as the effect.

Unit = auto-on players in `player_launch_cohort` (the holdout arm is excluded here and used only at the end, as the answer
key this design cannot see). Treatment = `got_autoclip_14d`; outcome = `retained_d14_27`.

**Can say:** the effect under *no unmeasured confounding* given these covariates. **Cannot say:** whether that assumption holds —
the latent "engagement tier" that drives both is only partly captured by pre-period activity. The E-value puts a number on how
strong the hidden confounder would need to be."""))

C.append(md("## 0 · Setup and the naive gap (the trap)"))
C.append(code(r"""import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0, '__NBDIR__')
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from IPython.display import Markdown, display
import medal_nb as mn
from monaco import causal as cz
mn.setup()
T = mn.load('player_launch_cohort')
coh = T['player_launch_cohort']; coh['game'] = coh.game_id.map(mn.NAME)
on = coh[coh.autoclip_holdout == 0].copy()
COV = ['pre28_sessions', 'pre28_minutes', 'pre28_manual_clips', 'pre28_shares', 'tenure_days_at_launch', 'premium', 'steam_linked']
for g, c in on.groupby('game'):
    r = mn.rate_table(c, 'got_autoclip_14d', ['retained_d14_27'])
    print(f'\n== {g}: retention d14–27 by whether the player got an auto-clip in the first 14 days (auto-on arm only)'); print(r.round(3).to_string())
    print(f"naive gap: {(r.loc[1, 'retained_d14_27_rate'] - r.loc[0, 'retained_d14_27_rate']) * 100:+.1f} pp")
print('\nWhy it is a trap: pre-period activity differs by arm →'); print(on.groupby(['game', 'got_autoclip_14d'])[COV[:4]].mean().round(2).to_string())"""))

C.append(md("## 1 · Propensity model and overlap"))
C.append(code(r"""IPW = {}
for g, c in on.groupby('game'):
    res, bal, ov = cz.ipw(c, 'got_autoclip_14d', 'retained_d14_27', COV, estimand='ATT', n_boot=300)
    IPW[g] = (res, bal, ov)
    print(f"\n== {g}: n treated {res['n_treated']}, control {res['n_control']}, trimmed {res['n_trimmed']}; ESS treated {res['ess_treated']:.0f}, control {res['ess_control']:.0f}; max weight {res['max_weight']:.1f}")
    fig, note = cz.plot_overlap(ov, 'got_autoclip_14d'); fig.axes[0].set_title(f'{g}: overlap', loc='left', fontsize=10.8, fontweight='bold', pad=22); plt.show(); print(note)"""))

C.append(md("## 2 · Balance before and after weighting"))
C.append(code(r"""for g, (res, bal, ov) in IPW.items():
    print(f'\n== {g}'); print(bal.round(3).to_string())
    fig, note = cz.plot_balance(bal); fig.axes[0].set_title(f'{g}: covariate balance', loc='left', fontsize=10.8, fontweight='bold', pad=22); plt.show(); print(note)"""))

C.append(md("## 3 · The weighted effect, next to the naive gap and the randomized answer this design cannot see"))
C.append(code(r"""rows = []
for g, c in coh.groupby('game'):
    res = IPW[g][0]
    itt = mn.arm_table(c, 'autoclip_holdout', ['retained_d14_27'], treat=0).loc['retained_d14_27']
    p1 = c.loc[(c.autoclip_holdout == 0) & (c.got_autoclip_14d == 1), 'retained_d14_27'].mean()
    p0 = c.loc[(c.autoclip_holdout == 0) & (c.got_autoclip_14d == 0), 'retained_d14_27'].mean()
    rr_naive = p1 / p0; rr_ipw = (p0 + res['effect']) / p0
    rows.append(dict(game=g, naive_pp=res['naive_diff'] * 100, ipw_att_pp=res['effect'] * 100, ipw_lo_pp=res['lo'] * 100, ipw_hi_pp=res['hi'] * 100,
                     holdout_itt_pp=itt['diff'] * 100, itt_lo_pp=itt.lo * 100, itt_hi_pp=itt.hi * 100,
                     evalue_naive=mn.evalue(rr_naive), evalue_ipw=mn.evalue(rr_ipw)))
CMP = pd.DataFrame(rows).set_index('game')
print(CMP.round(2).to_string())
fig, ax = plt.subplots(figsize=(8.5, 3.4))
y = np.arange(len(CMP)); h = 0.26
ax.barh(y + h, CMP.naive_pp, height=h, color=mn.O_PALE, label='naive: got vs not')
ax.barh(y, CMP.ipw_att_pp, height=h, color=mn.O_MID, label='IPW ATT: got vs not, reweighted on pre covariates')
ax.errorbar(CMP.ipw_att_pp, y, xerr=[CMP.ipw_att_pp - CMP.ipw_lo_pp, CMP.ipw_hi_pp - CMP.ipw_att_pp], fmt='none', ecolor=mn.BLACK, capsize=2)
ax.barh(y - h, CMP.holdout_itt_pp, height=h, color=mn.BLACK, label='randomized ITT: offered vs holdout (the answer key)')
ax.errorbar(CMP.holdout_itt_pp, y - h, xerr=[CMP.holdout_itt_pp - CMP.itt_lo_pp, CMP.itt_hi_pp - CMP.holdout_itt_pp], fmt='none', ecolor=mn.O_DARK, capsize=2)
for yy, (a, b, c_) in enumerate(zip(CMP.naive_pp, CMP.ipw_att_pp, CMP.holdout_itt_pp)):
    ax.text(a, yy + h, f' {a:+.1f}', va='center', fontsize=8); ax.text(max(b, 0), yy, f' {b:+.1f}', va='center', fontsize=8); ax.text(max(c_, 0), yy - h, f' {c_:+.1f}', va='center', fontsize=8)
ax.set_yticks(y, CMP.index); ax.axvline(0, color=mn.GRAY, lw=1); ax.legend(fontsize=7.5, loc='lower right'); ax.grid(axis='x'); ax.set_xlabel('retention d14–27, percentage points')
mn.titled(ax, 'IPW moves the naive gap toward the truth but does not reach it', 'the covariates capture part of the engagement tier; the rest is unmeasured — by construction of the data, and plausibly of real data too')
plt.show()
print('\nE-value: an unmeasured confounder would need a risk ratio of at least this size with BOTH getting a clip and returning, to explain the estimate away. Pre-period activity itself has RR ~2–3 with both, so the bar is not high.')"""))

C.append(md("## 4 · Sensitivity: what the estimate does as covariates are removed"))
C.append(code(r"""rows = []
for g, c in on.groupby('game'):
    for k in range(len(COV), 0, -1):
        cov = COV[:k]
        res, _, _ = cz.ipw(c, 'got_autoclip_14d', 'retained_d14_27', cov, estimand='ATT', n_boot=100)
        rows.append(dict(game=g, n_covariates=k, last_included=cov[-1], att_pp=res['effect'] * 100, lo=res['lo'] * 100, hi=res['hi'] * 100, ess_control=res['ess_control']))
SENS = pd.DataFrame(rows); print(SENS.round(1).to_string(index=False))
print('\nRead: the estimate should move monotonically toward the randomized answer as the activity covariates come in; the gap that remains with all seven is the unobserved part.')"""))

C.append(md("## 5 · Close"))
C.append(code(r"""for g in ('Rocket League', 'Ghost Janitors'):
    r = CMP.loc[g]
    head = (f"IPW on pre-launch activity: getting an auto-clip is associated with {r.ipw_att_pp:+.1f} pp retention d14–27 (CI {r.ipw_lo_pp:+.1f}…{r.ipw_hi_pp:+.1f}), down from a naive {r.naive_pp:+.1f} pp; "
            f"E-value {r.evalue_ipw:.2f}. The randomized holdout, which this design cannot see, says {r.holdout_itt_pp:+.1f} pp (CI {r.itt_lo_pp:+.1f}…{r.itt_hi_pp:+.1f}).")
    go = 'Do not ship a retention claim on this: the weighted estimate still sits above the randomized one, so residual selection remains' if r.ipw_att_pp > r.itt_hi_pp else 'The weighted estimate is inside the randomized CI: usable as a directional read, not as a number'
    action = 'if no holdout exists at the next launch, log the pre-period covariates at the player level from day 0 and pre-register the IPW spec; it is the best available fallback, and it should be reported next to its E-value.'
    guard = 'any IPW estimate whose E-value is below the observed risk ratio between pre-period activity and retention (~2) is not robust and must not reach a studio deck.'
    revisit = 'with a doubly-robust estimator (outcome model + weights) and with exposure defined on the player-day, where the within-player comparison removes the tier entirely (fixed effects).'
    display(Markdown(mn.close_md(g, head, go, action, guard, revisit)))"""))

C.append(md("""## 6 · Limits of this approach
- No unmeasured confounding is an assumption, not a result; the balance table is necessary, not sufficient.
- Overlap trimming drops the heaviest players (propensity near 1): the estimate is for a narrower population than the one the studio asks about.
- Treatment here is "received a clip", which is downstream of play; the policy question is "offered the feature". Only the holdout answers that.
- Agreement across 02 → 05 on the sign is the message; the size is only trustworthy from the randomized design."""))

if __name__ == "__main__":
    for c in C:
        if c.cell_type == "code":
            c.source = c.source.replace("__NBDIR__", str(NB))
    OUT.mkdir(parents=True, exist_ok=True)
    build_and_execute(nb, str(OUT / "05_ipw_got_autoclip.ipynb"), workdir=str(OUT))
