"""Notebook 01 — the packet-only answer: pre/post against a projected baseline.

This is the approach the live interview forces: aggregate tabs only (daily per game, 14D outcomes by trigger class, trigger
breakdown, return rate, platform, Ghost Janitors external). Identification = interrupted time series on log(metric) with a
weekday pattern, fit on the 8 weeks before launch and projected over days 14–41 after it; per-player rates so player-count
swings (seasons, esports, summer) net out. Weakest rung of the causal ladder; the notebook says so.

    python3 datasets/medal/nb/build_01_packet_prepost.py   ->  datasets/medal/out/notebooks/01_packet_prepost.ipynb
"""
from pathlib import Path

from monaco.viz import build_and_execute, code, md, new_notebook

NB = Path(__file__).resolve().parent
OUT = NB.parent / "out" / "notebooks"
nb = new_notebook(); C = nb.cells

C.append(md("""# Medal auto-clipping — 01 · the packet-only answer (pre/post vs projected baseline)

**Objective (from the case prompt):** assess the impact of auto-clipping on metrics for the platform and for the game.
Business goals: *grow data volume · improve on-platform engagement · drive successful outcomes for games and studios
(engagement, copies sold)*. Games: **Rocket League** (free-to-play, launched 2026-05-07) and **Ghost Janitors** (paid co-op horror,
launched 2026-05-21).

**Approach in this notebook:** only what the interview packet contains — daily per-game aggregates, 14-day outcomes by trigger
class, trigger breakdown, return rate, platform table, Ghost Janitors external feed. The estimator is an interrupted time
series: `log(metric) ~ level + weekday` fit on the 56 days before launch, projected over days 14–41 after launch (the first two
weeks are the client-update ramp). Lift = actual / projected − 1, with a 95% CI that includes projection error and day-to-day
autocorrelation. **Per-player rates** are the read; raw counts move with seasons, esports events and summer.

**What this approach can say:** the size of the step at launch net of weekday and level. **What it cannot say:** whether the
step is auto-clipping or anything else that changed in May (RLCS Major, a discount, a patch, school holidays). Notebooks 02 and 03
answer the same questions with a randomized holdout and with control games."""))

C.append(md("## 0 · Setup and the frame"))
C.append(code(r"""import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0, '__NBDIR__')
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from IPython.display import Markdown, display
import medal_nb as mn
mn.setup()
T = mn.load('game_daily', 'outcomes_14d_by_trigger', 'trigger_breakdown', 'return_rate', 'studio_daily', 'platform', 'games')
for k, v in T.items(): print(f'{k:<26} {len(v):>6,} rows  cols={list(v.columns)[:6]}…')
frame = pd.DataFrame([
    ('Medal',   'data volume',        'clips captured; manual (hotkey) clips — did auto-clips cannibalise them?'),
    ('Medal',   'engagement',         'shares off-Medal and public posts PER PLAYER (per-clip rates dilute mechanically)'),
    ('Players', 'curation burden',    'deletions per player; 14-day delete rate by trigger class'),
    ('Studio',  'engagement / sales', 'RL: Medal players in game (confounded); GJ: DAU, wishlists, copies — per DAU, net of whole-game swings'),
], columns=['stakeholder', 'goal', 'metric and the trap'])
print(frame.to_string(index=False))"""))

C.append(md("## 1 · Platform context: where the two games sit, and what auto-clipping does to per-clip rates"))
C.append(code(r"""p = T['platform'].copy()
p['auto_share'] = p.clips_autoclip / p.clips_total
p['delete_ev_per_clip'] = p.delete_events / p.clips_total
p['share_ev_per_clip'] = p.share_events / p.clips_total
p = p.sort_values('clips_total', ascending=False).reset_index(drop=True)
print(p[['game', 'clips_total', 'auto_share', 'delete_ev_per_clip', 'share_ev_per_clip']].to_string(index=False, formatters={
    'clips_total': '{:,.0f}'.format, 'auto_share': '{:.0%}'.format, 'delete_ev_per_clip': '{:.2f}'.format, 'share_ev_per_clip': '{:.3f}'.format}))
corr = p[['auto_share', 'delete_ev_per_clip', 'share_ev_per_clip']].corr().loc['auto_share']
print(f"\ncorr(auto share, delete events/clip) = {corr['delete_ev_per_clip']:+.2f}; corr(auto share, share events/clip) = {corr['share_ev_per_clip']:+.2f}")
fig, ax = plt.subplots(figsize=(8, 5))
focus = p.game.isin(['Rocket League', 'Ghost Janitors'])
for sub, col in ((p[~focus], mn.GRAY), (p[focus], mn.O_DARK)):
    ax.scatter(sub.auto_share, sub.share_ev_per_clip, s=40, color=col, zorder=3, label='share events / clip' if col == mn.GRAY else None)
    ax.scatter(sub.auto_share, sub.delete_ev_per_clip, s=40, color=col, marker='x', zorder=3, label='delete events / clip' if col == mn.GRAY else None)
for _, r in p[focus].iterrows():
    ax.annotate(r.game, (r.auto_share, r.delete_ev_per_clip), xytext=(5, 3), textcoords='offset points', fontsize=8.5, color=mn.O_DARK)
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.0%}')); ax.set_xlabel('auto-clip share of clips'); ax.set_ylabel('events per clip')
ax.legend(fontsize=8)
mn.titled(ax, 'More auto-clipping → more deletes and fewer shares PER CLIP across the platform',
          'each dot/cross is a game, Feb 1 – Aug 31 · events, not distinct clips · orange = the two case games')
plt.show()
print('Read: per-clip ratios fall mechanically as auto-clips inflate the denominator. Judge engagement per PLAYER from here on.')"""))

for gid, key in ((1, 'rl'), (2, 'gj')):
    name = {1: 'Rocket League', 2: 'Ghost Janitors'}[gid]
    C.append(md(f"## {gid + 1} · {name}: composition, scorecard, per-player rates vs projected baseline"))
    C.append(code(rf"""gid, name, L = {gid}, '{name}', mn.LAUNCH[{gid}]
d = mn.derive_daily(T['game_daily'], gid)
print('missing days in the daily tab:', list(d.index[d.players.isna()].date))
purge = mn.spikes(d.deletes_pp) & (d.clips_deleted_distinct > 0)
sc, res = mn.scorecard(d, L, exclude=purge)
{key.upper()} = dict(d=d, res=res, purge=purge)
print(f'PRE = {{mn.PRE}} days before launch · skip {{mn.RAMP}}-day ramp · POST = {{mn.POST}} days · baseline fit on {{mn.FIT}} days')
print(mn.fmt_scorecard(sc).to_string(index=False))
if purge.any(): print('deletion spikes excluded from the deletion fit:', [(a.date(), b.date()) for a, b in mn.spans(purge)])
mn.plot_composition(d, L, name); plt.show()
mn.plot_metrics(d, L, res, ['manual_pp', 'shares_pp', 'pct_sharing', 'share_per_clip', 'deletes_pp', 'players'],
                f'{{name}}: per-player behaviour vs pre-launch baseline', exclude=purge); plt.show()
post = d[(d.index >= L + mn.D(mn.RAMP)) & (d.index < L + mn.D(mn.RAMP + mn.POST))]
print(f"auto-clips add {{post.clips_auto.mean():,.0f}}/day = {{post.clips_auto.sum() / post.clips_total.sum():.0%}} of {{name}} clips in POST; "
      f"manual clips/player {{res['manual_pp']['lift']:+.1%}} vs baseline ({{res['manual_pp']['call']}}); shares/player {{res['shares_pp']['lift']:+.1%}} ({{res['shares_pp']['call']}}) "
      f"while shares/clip went {{res['share_per_clip']['pre']:.1%}} → {{res['share_per_clip']['post']:.1%}} — dilution, not decline.")"""))
    C.append(md(f"### {gid + 1}.1 · {name}: 14-day outcomes by trigger class, keepers vs junk, the pruning trade-off"))
    C.append(code(rf"""o = T['outcomes_14d_by_trigger']; o = o[(o.game_id == gid) & (o.week >= L - pd.Timedelta(days=L.dayofweek) + pd.Timedelta(days=7))]
cls = o.groupby('trigger_class')[['clips_captured', 'deleted_within_14d', 'shared_within_14d', 'public_posts']].sum()
for k in ('deleted_within_14d', 'shared_within_14d', 'public_posts'):
    p_, lo, hi = mn.wilson(cls[k].values, cls.clips_captured.values); cls[k.split('_')[0] + '_rate'] = p_; cls[k.split('_')[0] + '_ci'] = [f'{{a:.1%}}–{{b:.1%}}' for a, b in zip(lo, hi)]
cls['pct_of_clips'] = cls.clips_captured / cls.clips_captured.sum(); cls['pct_of_shares'] = cls.shared_within_14d / cls.shared_within_14d.sum()
print('post-launch weeks (launch week excluded), server record — compare classes to each other, never to the daily tab:')
print(cls.round(3).to_string())
t = T['trigger_breakdown']; t = t[t.game_id == gid].copy()
t['n'] = t.clips_captured
for f, k in (('shared_within_14d', 'shared'), ('deleted_within_14d', 'deleted')):
    t[f'{{k}}_k'] = t[f]; t[f'{{k}}_rate'], t[f'{{k}}_lo'], t[f'{{k}}_hi'] = mn.wilson(t[f].values, t.n.values)
t['thin'] = t.n < 30; t = t.set_index('trigger_name')
avg_s, avg_d = t.shared_k.sum() / t.n.sum(), t.deleted_k.sum() / t.n.sum()
t['verdict'] = np.select([(t.shared_rate >= avg_s) & (t.deleted_rate <= avg_d), (t.shared_rate < .6 * avg_s) & (t.deleted_rate > avg_d)], ['keeper', 'junk'], 'middling')
t['pct_volume'] = t.n / t.n.sum()
print(t[['n', 'pct_volume', 'shared_rate', 'deleted_rate', 'verdict']].sort_values('shared_rate', ascending=False).round(3).to_string())
mn.barh_rates(t, 'shared', f'{{name}}: 14-day share rate per auto-clip trigger', 'Wilson 95% intervals · dashed = all auto-clips', ref=avg_s); plt.show()
mn.barh_rates(t, 'deleted', f'{{name}}: 14-day delete rate per auto-clip trigger', 'Wilson 95% intervals · dashed = all auto-clips', ref=avg_d, color=mn.O_DARK); plt.show()
# pruning trade-off: turn triggers off from the worst share rate up; what % of auto volume (and deletions) goes vs % of auto shares lost
cur = t.sort_values('shared_rate')[['n', 'shared_k', 'deleted_k']].cumsum() / t[['n', 'shared_k', 'deleted_k']].sum()
cur.columns = ['volume_removed', 'shares_lost', 'deletions_removed']
print(cur.round(3).to_string())
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(cur.volume_removed, cur.shares_lost, color=mn.BLACK, marker='o', lw=1.8, label='auto shares lost')
ax.plot(cur.volume_removed, cur.deletions_removed, color=mn.O_MID, marker='o', lw=1.8, label='auto deletions removed')
for i, (x, y1) in enumerate(zip(cur.volume_removed, cur.shares_lost)): ax.annotate(cur.index[i], (x, y1), xytext=(4, -10), textcoords='offset points', fontsize=7.5)
ax.plot([0, 1], [0, 1], color=mn.GRAY, ls=':', lw=1); ax.set_xlabel('share of auto-clip volume turned off'); ax.set_ylabel('share of …')
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{{v:.0%}}')); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{{v:.0%}}')); ax.legend(fontsize=8)
mn.titled(ax, f'{{name}}: the pruning trade-off', 'triggers switched off worst-first (by share rate); below the diagonal = cheap to cut')
plt.show()
junk = t[t.verdict == 'junk']
{key.upper()}['prune'] = dict(triggers=list(junk.index), vol=junk.pct_volume.sum(), shares=junk.shared_k.sum() / t.shared_k.sum(), dels=junk.deleted_k.sum() / t.deleted_k.sum())
print(f"prune set {{list(junk.index)}}: −{{{key.upper()}['prune']['vol']:.0%}} of auto volume, −{{{key.upper()}['prune']['dels']:.0%}} of auto deletions, for −{{{key.upper()}['prune']['shares']:.0%}} of auto shares")"""))

C.append(md("## 4 · Return rate: what the packet's table can and cannot say"))
C.append(code(r"""rr = T['return_rate'].copy()
for k in ('returned_wk2', 'returned_wk5'):
    rr[k + '_rate'], rr[k + '_lo'], rr[k + '_hi'] = mn.wilson(rr[k].values, rr.players.values)
rr['game'] = rr.game_id.map(mn.NAME)
print(rr[['game', 'got_autoclip', 'players', 'returned_wk2_rate', 'returned_wk2_lo', 'returned_wk2_hi', 'returned_wk5_rate']].round(3).to_string(index=False))
gap = rr.pivot(index='game', columns='got_autoclip', values='returned_wk2_rate'); gap['gap_pp'] = (gap[True] - gap[False]) * 100
print(gap.round(3).to_string())
print('\nSelection, not effect: a player only receives a goal / jump-scare clip on a day they played long enough to trigger one, and such players '
      'return more regardless. The packet has no pre-period or holdout to correct this. Notebook 02 does.')"""))

C.append(md("## 5 · Ghost Janitors studio metrics: DAU, wishlists, copies — net of whole-game swings"))
C.append(code(r"""e = T['studio_daily']; e = e[e.game_id == 2]
print('duplicate dates in the external feed:', int(e.date.duplicated().sum()), '→ dropped')
e = e.drop_duplicates('date').set_index('date').asfreq('D')
L = mn.LAUNCH[2]
sale = mn.spikes(e.copies_sold, window=31, ratio=1.8)
print('sale-like copies spikes (excluded from fits):', [(a.date(), b.date()) for a, b in mn.spans(sale)])
e['wishlists_per_dau'] = e.wishlists / e.dau; e['copies_per_dau'] = e.copies_sold / e.dau
e['medal_per_dau'] = GJ['d'].players / e.dau
EXT = {}
for m in ('dau', 'wishlists', 'copies_sold', 'wishlists_per_dau', 'copies_per_dau', 'medal_per_dau'):
    EXT[m] = mn.assess(e[m], L, exclude=sale); mn.LABEL[m] = m
    r = EXT[m]; print(f"{m:<18} pre {r['pre']:>9,.3f}  post {r['post']:>9,.3f}  naive {r['naive']:+.1%}  vs baseline {r['lift']:+.1%}  CI {r['lo']:+.1%} … {r['hi']:+.1%}  → {r['call']}")
pen = EXT['medal_per_dau']; print(f"\nMedal penetration of GJ DAU: {pen['pre']:.1%} pre → {pen['post']:.1%} post — caps any direct effect; the channel is shares → strangers.")
mn.plot_metrics(e, L, EXT, ['dau', 'wishlists', 'copies_sold', 'wishlists_per_dau', 'copies_per_dau', 'medal_per_dau'], 'Ghost Janitors (external): studio metrics around the auto-clip launch'); plt.show()
# plausibility: how many wishlists / copies per auto-clip share would the lift imply?
post = GJ['d'][(GJ['d'].index >= L + mn.D(mn.RAMP)) & (GJ['d'].index < L + mn.D(mn.RAMP + mn.POST))]
auto_shares_day = post.clips_autoclip_native.mean() * cls.loc['autoclip_native', 'shared_rate'] if 'autoclip_native' in cls.index else np.nan
for m, lbl in (('wishlists', 'wishlists'), ('copies_sold', 'copies')):
    r = EXT[m]; cf_day = r['post'] / (1 + r['lift']) if not np.isnan(r['lift']) else np.nan
    print(f"{lbl}: lift {r['lift']:+.1%} on ~{cf_day:,.0f}/day baseline = {r['lift'] * cf_day:+,.1f}/day; auto-clip shares ≈ {auto_shares_day:,.1f}/day → implied {r['lift'] * cf_day / auto_shares_day:,.2f} {lbl} per share "
          f"(a shared clip reaches a Discord, not a storefront: >2 wishlists or >0.5 copies per share is implausible)")
print('\nWeeks with a sale-like spike or a DAU jump sit inside the post window → the per-DAU lift is the only read that survives, and it is still pre/post.')"""))

C.append(md("## 6 · Close — one per game, every number from the cells above"))
C.append(code(r"""def pct(x): return 'n/a' if pd.isna(x) else f'{x:+.0%}'
for key, A in (('rl', RL), ('gj', GJ)):
    name = {'rl': 'Rocket League', 'gj': 'Ghost Janitors'}[key]; r = A['res']; pr = A['prune']
    d = A['d']; L = mn.LAUNCH[1 if key == 'rl' else 2]
    post = d[(d.index >= L + mn.D(mn.RAMP)) & (d.index < L + mn.D(mn.RAMP + mn.POST))]
    cannibal = r['manual_pp']['call'] == 'DOWN'
    head = (f"auto-clipping adds ~{post.clips_auto.mean():,.0f} clips/day ({post.clips_auto.sum() / post.clips_total.sum():.0%} of {name} clips); manual clips/player {pct(r['manual_pp']['lift'])} "
            f"vs baseline ({r['manual_pp']['call']}, CI {r['manual_pp']['lo']:+.0%}…{r['manual_pp']['hi']:+.0%}); shares/player {pct(r['shares_pp']['lift'])} ({r['shares_pp']['call']}) "
            f"while shares/clip fell {r['share_per_clip']['pre']:.1%} → {r['share_per_clip']['post']:.1%}.")
    if key == 'gj':
        w = EXT['wishlists_per_dau']; c = EXT['copies_per_dau']
        head += (f" Studio: wishlists per DAU {pct(w['lift'])} ({w['call']}), copies per DAU {pct(c['lift'])} ({c['call']}); Medal reaches {EXT['medal_per_dau']['post']:.1%} of DAU, "
                 f"and a sale-like spike sits in the window — the studio read is pre/post only.")
    go = ('GO with a cannibalization guardrail' if cannibal else 'GO') + (f" — prune {', '.join(pr['triggers'])}" if pr['triggers'] else '')
    go += '; the studio-impact claim is NOT supportable from this packet (no control, discount in window)' if key == 'gj' else ''
    action = (f"turn off {', '.join(pr['triggers'])} (−{pr['vol']:.0%} auto volume, −{pr['dels']:.0%} auto deletions, −{pr['shares']:.0%} auto shares) and lead the studio pitch with the keeper triggers; "
              f"deletions/player {pct(r['deletes_pp']['lift'])} is the curation cost to show next to the volume gain.")
    guard = f"manual clips/player below {r['manual_pp']['pre'] * 0.9:.2f} (−10% vs pre) for two consecutive weeks, or shares/player back to the pre level {r['shares_pp']['pre']:.3f}."
    revisit = "a randomized holdout (auto-clip off for a share of players) is the only way to read retention and the studio funnel causally — notebook 02 shows what that gives."
    display(Markdown(mn.close_md(name, head, go, action, guard, revisit)))"""))

C.append(md("""## 7 · Limits of this approach (say them before anyone asks)
- No control: the baseline is a projection, so every May event (RLCS Major May 20–26, GJ launch-week discount, Jun 4 patch, summer) is inside the estimate.
- The 28-day POST window is short: CIs on per-player rates are ±5–8%, so a true −12% cannibalization can read "within noise".
- Return rate is selection; deletion counts are client-side and any-age; platform rates are events. None of those is a product effect.
- The right next step is not a better projection, it is a design: notebook 02 (holdout) and notebook 03 (control games)."""))

if __name__ == "__main__":
    for c in C:
        if c.cell_type == "code":
            c.source = c.source.replace("__NBDIR__", str(NB))
    OUT.mkdir(parents=True, exist_ok=True)
    build_and_execute(nb, str(OUT / "01_packet_prepost.ipynb"), workdir=str(OUT))
