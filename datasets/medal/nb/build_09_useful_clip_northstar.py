"""Notebook 09 — Case 2 prompt: "what is a useful clip (General Intuition), what does junk cost, and what should the north-star be?"

    python3 datasets/medal/nb/build_09_useful_clip_northstar.py   ->  datasets/medal/out/notebooks/09_useful_clip_northstar.ipynb
"""
from pathlib import Path

from monaco.viz import build_and_execute, code, md, new_notebook

NB = Path(__file__).resolve().parent
OUT = NB.parent / "out" / "notebooks"
nb = new_notebook(); C = nb.cells

C.append(md("""# Medal auto-clipping — 09 · Case 2: the useful clip, the cost of junk, and a north-star metric

**Likely prompts:** *"Medal's data trains General Intuition's world models. What makes a clip useful as training data, should
deleted clips count, and what does auto-clipping's junk cost us?"* and *"What should Medal's north-star metric be?"*

Definitions are made here, printed, and stress-tested: *useful* = kept 14 days ∧ an input log is attached ∧ motion score at or
above a threshold (dial). Storage cost is a $/GB-month dial. The north-star candidates are compared on three tests: does it move
with the feature (not mechanically), can a team game it, does it line up with the three business goals."""))

C.append(md("## 0 · Setup and the definition"))
C.append(code(r"""import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0, '__NBDIR__')
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from IPython.display import Markdown, display
import medal_nb as mn
from monaco.eda import penetration, pareto, distribution
mn.setup()
T = mn.load('clips', 'game_daily', 'sessions', 'games')
cl = T['clips'].drop_duplicates('clip_id'); cl = cl[cl.deleted_14d.notna()].copy()
cl['game'] = cl.game_id.map(mn.NAME); cl['trigger_name'] = cl.trigger_name.fillna('(hotkey)').str.title()
cl['kept_14d'] = 1 - cl.deleted_14d
THR = 0.5
cl['useful'] = ((cl.kept_14d == 1) & (cl.input_log_attached == 1) & (cl.motion_score >= THR)).astype(int)
cl['labelled_kept'] = ((cl.kept_14d == 1) & (cl.input_log_attached == 1)).astype(int)
print(f'definition: useful = kept 14d AND input_log_attached AND motion_score >= {THR}')
print(f"clips with a full 14 days: {len(cl):,}; useful {cl.useful.mean():.1%}; kept {cl.kept_14d.mean():.1%}; labelled {cl.input_log_attached.mean():.1%}; motion>=thr {(cl.motion_score >= THR).mean():.1%}")
sens = pd.DataFrame({t: cl.assign(u=((cl.kept_14d == 1) & (cl.input_log_attached == 1) & (cl.motion_score >= t))).groupby('trigger_class').u.mean() for t in (0.3, 0.5, 0.7)}).T
sens.index.name = 'motion threshold'; print('\nuseful share by trigger class as the motion threshold moves:'); print(sens.round(3).to_string())"""))

C.append(md("## 1 · Where useful clips come from: by trigger class, trigger, game"))
C.append(code(r"""for dim in ('trigger_class', 'game'):
    v = penetration(cl, dim, 'useful', flag_label='useful for training'); print(v.table.to_string()); print(v.note); plt.show()
auto = cl[cl.trigger_class == 'autoclip_native']
v = penetration(auto, 'trigger_name', 'useful', flag_label='useful for training', top_k=12); print(v.table.to_string()); print(v.note); plt.show()
print('\nRead: the junk triggers for sharing (Demolition, Assist, Job Complete…) are also the junk triggers for training — deletion is the common factor. Keepers are keepers on both counts.')"""))

C.append(md("## 2 · Volume vs usefulness: what auto-clipping added, and what the junk costs in storage"))
C.append(code(r"""post = cl[(cl.game_id.isin([1, 2])) & (cl.captured_ts >= cl.game_id.map(mn.LAUNCH))]
agg = post.groupby(['game', 'trigger_class']).agg(clips=('clip_id', 'size'), useful=('useful', 'sum'), kept=('kept_14d', 'sum'), storage_gb=('storage_mb', lambda x: x.sum() / 1024),
                                                  junk_gb=('storage_mb', lambda x: 0)).reset_index()
junk = post[post.useful == 0].groupby(['game', 'trigger_class']).storage_mb.sum() / 1024
agg['junk_gb'] = agg.set_index(['game', 'trigger_class']).index.map(junk).fillna(0).values
agg['useful_rate'] = agg.useful / agg.clips; agg['gb_per_useful'] = agg.storage_gb / agg.useful
print('post-launch clips with a full 14 days, by game × class (sample scale; ×40 for platform):'); print(agg.round(3).to_string(index=False))
GB = (0.02, 0.05); SCALE = 40
tot = agg.groupby('game')[['clips', 'useful', 'storage_gb', 'junk_gb']].sum()
tot['junk_cost_month_high'] = tot.junk_gb * SCALE * GB[1] / 3.5           # window ≈ 3.5 months post-launch
tot['useful_per_month'] = tot.useful * SCALE / 3.5
print('\nplatform-scale monthly: useful clips added vs $ of junk storage (at $0.05/GB-month):'); print(tot.round(0).to_string())
# the argument both ways on deleted clips
d = post.groupby('trigger_class').agg(deleted=('deleted_14d', 'mean'), labelled=('input_log_attached', 'mean'), motion=('motion_score', 'mean'),
                                     deleted_but_labelled_and_moving=('useful', lambda s: 0))
d['deleted_but_labelled_and_moving'] = post[(post.deleted_14d == 1) & (post.input_log_attached == 1) & (post.motion_score >= THR)].groupby('trigger_class').size() / post.groupby('trigger_class').size()
print('\nshould deleted clips count as data? share of each class that was deleted yet labelled and in motion:'); print(d.round(3).to_string())
print('For: deletion is a curation signal about the PLAYER\'s taste, not about the frames; a deleted Demolition still has a labelled input log. Against: a 48%-deleted trigger is also the one players did not want captured; keeping it costs storage and trust. Position: count them for training only if retention of deleted media is disclosed and capped at N days.')"""))

C.append(md("## 3 · Concentration: which players produce the useful clips"))
C.append(code(r"""v, tiers = pareto(cl, 'player_id', 'useful', label='useful clips by player'); print(v.table.to_string()); print(v.note); plt.show()
v2, tiers2 = pareto(cl, 'player_id', 'storage_mb', label='storage by player'); print(v2.table.to_string()); print(v2.note); plt.show()
print('\nIf the same small set of players produces most useful clips AND most storage, the lever is per-player (quality settings, premium), not per-trigger.')"""))

C.append(md("## 4 · North-star candidates, tested"))
C.append(code(r"""gd = T['game_daily']; S = T['sessions']
cand = {}
for gid in (1, 2):
    d = mn.derive_daily(gd, gid); L = mn.LAUNCH[gid]
    w = d.resample('W-SUN').sum(min_count=1)
    c = cl[cl.game_id == gid].assign(week=lambda x: x.captured_ts.dt.to_period('W-SUN').dt.start_time)
    wk = c.groupby('week').agg(kept_hours=('duration_s', lambda s: 0))
    wk['kept_hours'] = c[c.kept_14d == 1].groupby('week').duration_s.sum() / 3600
    wk['useful_clips'] = c[c.useful == 1].groupby('week').size()
    wk['players_keep_or_share'] = c[(c.kept_14d == 1) | (c.shared_14d == 1)].groupby('week').player_id.nunique()
    wk['clippers'] = c.groupby('week').player_id.nunique()
    wk['clips'] = c.groupby('week').size()
    s = S[S.game_id == gid].assign(week=lambda x: x.session_date - pd.to_timedelta(x.session_date.dt.dayofweek, unit='D')).groupby('week').player_id.nunique()
    wk['players'] = s.reindex(wk.index)
    wk['pct_players_keep_or_share'] = wk.players_keep_or_share / wk.players
    cand[gid] = wk[wk.index < wk.index.max()]
NS = ['clips', 'clippers', 'players_keep_or_share', 'pct_players_keep_or_share', 'useful_clips', 'kept_hours']
rows = []
for gid in (1, 2):
    wk = cand[gid]; L = mn.LAUNCH[gid]
    pre = wk[wk.index < L - mn.D(7)].tail(8); post = wk[(wk.index >= L + mn.D(mn.RAMP))].head(6)
    for m in NS:
        rows.append(dict(game=mn.NAME[gid], metric=m, pre_weekly=pre[m].mean(), post_weekly=post[m].mean(), change=post[m].mean() / pre[m].mean() - 1))
NST = pd.DataFrame(rows); print(NST.round(3).to_string(index=False))
fig, axes = plt.subplots(2, 3, figsize=(13, 6));
for ax, m in zip(axes.flat, NS):
    for gid, col in ((1, mn.BLACK), (2, mn.O_MID)):
        wk = cand[gid]; s = wk[m] / wk[wk.index < mn.LAUNCH[gid] - mn.D(7)].tail(8)[m].mean()
        ax.plot(s.index, s, color=col, lw=1.6, label=mn.NAME[gid]); ax.axvline(mn.LAUNCH[gid], color=col, ls='--', lw=.8)
    ax.axhline(1, color=mn.GRAY, lw=.8); ax.set_title(m, loc='left', fontsize=9.5, fontweight='bold')
axes[0, 0].legend(fontsize=8)
fig.suptitle('North-star candidates, weekly, indexed to the 8 weeks before launch: which ones move for real reasons?', x=0.01, ha='left', fontweight='bold')
fig.tight_layout(rect=(0, 0, 1, 0.94)); plt.show()
tests = pd.DataFrame([
    ('clips captured', 'mechanical ×2–3 at launch', 'yes — fire more triggers', 'data volume only', 'reject'),
    ('weekly clippers', 'mechanical (auto-clips make everyone a clipper)', 'yes', 'engagement, weakly', 'reject'),
    ('players who keep or share a clip (weekly)', 'moves only if players act on clips', 'hard — needs real curation', 'engagement + data quality', 'candidate'),
    ('% of players who keep or share', 'rate form of the above; robust to player-count swings', 'hard', 'engagement', 'candidate (guardrail form)'),
    ('useful clips (kept ∧ labelled ∧ moving)', 'moves with volume AND quality', 'medium — definition can be tuned', 'data volume for GI', 'candidate (GI north star)'),
    ('kept-clip hours', 'volume × retention; scales with duration', 'medium', 'data volume', 'secondary'),
], columns=['metric', 'does it move mechanically?', 'gameable?', 'aligned with', 'verdict'])
print(tests.to_string(index=False))"""))

C.append(md("## 5 · Close"))
C.append(code(r"""u = NST[(NST.metric == 'useful_clips')].set_index('game').change; k = NST[(NST.metric == 'players_keep_or_share')].set_index('game').change; c_ = NST[(NST.metric == 'clips')].set_index('game').change
display(Markdown(mn.close_md('Useful clips and the north star',
    f"Useful = kept ∧ labelled ∧ motion ≥ {THR}: {cl.useful.mean():.0%} of all clips, {cl[cl.trigger_class == 'hotkey'].useful.mean():.0%} of hotkey vs {cl[cl.trigger_class == 'autoclip_native'].useful.mean():.0%} of native auto-clips. "
    f"At launch, clips rose {c_['Rocket League']:+.0%} / {c_['Ghost Janitors']:+.0%} (mechanical) but useful clips {u['Rocket League']:+.0%} / {u['Ghost Janitors']:+.0%} and players-who-keep-or-share {k['Rocket League']:+.0%} / {k['Ghost Janitors']:+.0%}.",
    'Adopt weekly players who keep or share a clip as the platform north star (engagement), with useful clips per week as the GI data north star; retire raw clips captured as a headline.',
    'ship the two definitions as SQL views (kept = not deleted within 14 d of capture; useful adds input_log_attached and motion_score ≥ threshold); prune junk triggers, which are junk on both metrics.',
    f"junk storage: at $0.05/GB-month the junk auto-clips of the two games cost ~${tot.junk_cost_month_high.sum():,.0f}/month at platform scale — cap deleted-media retention and watch GB per useful clip.",
    'quarterly: re-test the motion threshold against GI\'s actual training yield; if the threshold moves the ranking of triggers, the metric is not stable enough to be a north star.')))"""))

C.append(md("""## 6 · Limits
- `input_log_attached` and `motion_score` are synthetic proxies for label quality; the real test is GI's training yield per clip.
- Deleted clips' media retention is a policy question (privacy, trust) before it is a data question.
- The north-star comparison uses 6 post-launch weeks; summer and the Steam sale sit inside them for Ghost Janitors.
- A metric that two teams can move in opposite directions (triggers vs curation) needs its guardrail stated next to it, as above."""))

if __name__ == "__main__":
    for c in C:
        if c.cell_type == "code":
            c.source = c.source.replace("__NBDIR__", str(NB))
    OUT.mkdir(parents=True, exist_ok=True)
    build_and_execute(nb, str(OUT / "09_useful_clip_northstar.ipynb"), workdir=str(OUT))
