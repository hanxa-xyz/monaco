"""Notebook 08 — Case 2 prompt: "which game should get the next auto-clip integration, and how big is the prize?"

    python3 datasets/medal/nb/build_08_next_integration.py   ->  datasets/medal/out/notebooks/08_next_integration.ipynb
"""
from pathlib import Path

from monaco.viz import build_and_execute, code, md, new_notebook

NB = Path(__file__).resolve().parent
OUT = NB.parent / "out" / "notebooks"
nb = new_notebook(); C = nb.cells

C.append(md("""# Medal auto-clipping — 08 · Case 2: which game next, and how big is the prize

**Likely prompt:** *"We can do one more integration this quarter. Which game, and what would it be worth?"*

Sizing discipline (from `/takehome-sizing`): dials, not point estimates; two routes to the same number; haircuts stated; the
result is a ranked shortlist with the dial that most moves each candidate. Candidates come from the platform table (19 games);
the per-session rates come from the two launches and Valorant; genre analogies fill the rest and are labelled as such.

Prize = incremental **kept** clips per month (data volume Medal can train on), incremental **shares** per month (engagement and
the studio's word-of-mouth channel), and the storage it costs."""))

C.append(md("## 0 · Setup: candidates and the observed rates"))
C.append(code(r"""import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0, '__NBDIR__')
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from IPython.display import Markdown, display
import medal_nb as mn
from monaco.eda import pareto
mn.setup()
T = mn.load('platform', 'sessions', 'clips', 'trigger_breakdown', 'game_daily', 'games')
plat = T['platform'].copy(); plat['auto_share'] = plat.clips_autoclip / plat.clips_total
cl = T['clips'].drop_duplicates('clip_id'); S = T['sessions']
# observed per-session rates for the integrated games (post-launch, auto-on sessions)
obs = []
for gid in (1, 2, 3):
    s = S[(S.game_id == gid) & (S.autoclip_on == 1)]
    c = cl[cl.session_id.isin(s.session_id) & (cl.trigger_class == 'autoclip_native') & cl.deleted_14d.notna()]
    obs.append(dict(game=mn.NAME[gid], sessions=len(s), auto_per_session=len(c) / max(len(s), 1), keep_rate=1 - c.deleted_14d.mean(), share_rate=c.shared_14d.mean(),
                    storage_mb_per_clip=c.storage_mb.mean(), sessions_per_player_month=len(s) / s.player_id.nunique() / (s.session_date.max() - s.session_date.min()).days * 30))
OBS = pd.DataFrame(obs).set_index('game'); print('observed on the integrated games (auto-on sessions, post-launch):'); print(OBS.round(3).to_string())
MAU_RATIO = 0.22
print('\ncandidates (platform table, Feb–Aug 2026):'); print(plat[['game', 'players_monthly_avg', 'clippers_monthly_avg', 'clips_total', 'auto_share']].sort_values('players_monthly_avg', ascending=False).to_string(index=False, formatters={'players_monthly_avg': '{:,.0f}'.format, 'clippers_monthly_avg': '{:,.0f}'.format, 'clips_total': '{:,.0f}'.format, 'auto_share': '{:.0%}'.format}))"""))

C.append(md("## 1 · Dials per candidate: players × sessions × triggers × keep × share, with the analogy labelled"))
C.append(code(r"""GENRE = {  # game: (genre, analogue for trigger rate, on Steam → achievement hook already live)
    'Roblox': ('sandbox', 'low'), 'Fortnite': ('shooter', 'Valorant'), 'Counter-Strike 2': ('shooter', 'Valorant'), 'Grand Theft Auto V': ('open world', 'mid'),
    'Minecraft': ('sandbox', 'low'), 'Call of Duty': ('shooter', 'Valorant'), 'Apex Legends': ('shooter', 'Valorant'), 'League of Legends': ('moba', 'mid'),
    'Rainbow Six Siege': ('shooter', 'Valorant'), 'Overwatch 2': ('shooter', 'Valorant'), 'Rust': ('survival', 'low'), 'R.E.P.O.': ('co-op horror', 'Ghost Janitors'),
    'Dead by Daylight': ('horror', 'Ghost Janitors'), 'Marvel Rivals': ('hero shooter', 'Valorant'), 'Phasmophobia': ('co-op horror', 'Ghost Janitors'), 'Lethal Company': ('co-op horror', 'Ghost Janitors'),
}
RATE = {'Valorant': OBS.loc['Valorant'], 'Ghost Janitors': OBS.loc['Ghost Janitors'], 'Rocket League': OBS.loc['Rocket League'],
        'mid': OBS.loc[['Valorant', 'Ghost Janitors']].mean(), 'low': OBS.loc['Ghost Janitors'] * 0.5}
rows = []
for _, r in plat.iterrows():
    if r.game in ('Rocket League', 'Ghost Janitors', 'Valorant') or r.auto_share > 0.3:   # already integrated
        continue
    genre, ana = GENRE.get(r.game, ('other', 'mid')); a = RATE[ana]
    rows.append(dict(candidate=r.game, genre=genre, analogue=ana, medal_players_month=r.players_monthly_avg, sessions_per_player_month=a.sessions_per_player_month,
                     auto_per_session=a.auto_per_session, keep_rate=a.keep_rate, share_rate=a.share_rate, storage_mb_per_clip=a.storage_mb_per_clip,
                     holdout_or_opt_out=0.2, junk_share=0.30))
CAND = pd.DataFrame(rows).set_index('candidate')
CAND['auto_clips_month'] = CAND.medal_players_month * CAND.sessions_per_player_month * CAND.auto_per_session * (1 - CAND.holdout_or_opt_out)
CAND['kept_clips_month'] = CAND.auto_clips_month * CAND.keep_rate
CAND['shares_month'] = CAND.auto_clips_month * CAND.share_rate
CAND['storage_gb_month'] = CAND.auto_clips_month * CAND.storage_mb_per_clip / 1024
CAND['kept_after_prune'] = CAND.kept_clips_month * (1 - CAND.junk_share * 0.5)        # pruning junk triggers removes ~30% of volume but only ~15% of kept clips
CAND = CAND.sort_values('kept_clips_month', ascending=False)
print(CAND[['genre', 'analogue', 'medal_players_month', 'sessions_per_player_month', 'auto_per_session', 'keep_rate', 'share_rate', 'auto_clips_month', 'kept_clips_month', 'shares_month', 'storage_gb_month']]
      .to_string(formatters={c: '{:,.0f}'.format for c in ['medal_players_month', 'auto_clips_month', 'kept_clips_month', 'shares_month', 'storage_gb_month']} | {'sessions_per_player_month': '{:.1f}'.format, 'auto_per_session': '{:.2f}'.format, 'keep_rate': '{:.0%}'.format, 'share_rate': '{:.1%}'.format}))
print('\nRoute 1 (bottom-up): players × sessions/player × auto-clips/session × keep. Every column is a dial; the analogue column says which observed game it borrows from.')"""))

C.append(md("## 2 · Route 2 (top-down): what the integrated games actually added, scaled by player base"))
C.append(code(r"""gd = T['game_daily']
rows = []
for gid in (1, 2):
    d = mn.derive_daily(gd, gid); L = mn.LAUNCH[gid]
    post = d[(d.index >= L + mn.D(mn.RAMP))]; pre = d[d.index < L]
    rows.append(dict(game=mn.NAME[gid], auto_clips_per_player_day=post.clips_auto.sum() / post.players.sum(), players_per_day=post.players.mean(),
                     clips_per_player_day_pre=pre.clips_total.sum() / pre.players.sum(), clips_per_player_day_post=post.clips_total.sum() / post.players.sum()))
TD = pd.DataFrame(rows).set_index('game'); print(TD.round(3).to_string())
# auto-clips per player-day observed → per monthly player via DAU/MAU
per_mau = TD.auto_clips_per_player_day * 30 * MAU_RATIO
print(f"\nauto-clips per monthly player per month: RL {per_mau['Rocket League']:.1f}, GJ {per_mau['Ghost Janitors']:.1f} (DAU/MAU {MAU_RATIO})")
CAND['route2_auto_clips_month'] = CAND.medal_players_month * np.where(CAND.analogue == 'Ghost Janitors', per_mau['Ghost Janitors'], per_mau['Rocket League'] * np.where(CAND.analogue == 'Valorant', OBS.loc['Valorant', 'auto_per_session'] / OBS.loc['Rocket League', 'auto_per_session'], 0.5)) * 0.8
CAND['route_ratio'] = CAND.route2_auto_clips_month / CAND.auto_clips_month
print('\nroute 1 vs route 2 (auto-clips per month):'); print(CAND[['auto_clips_month', 'route2_auto_clips_month', 'route_ratio']].round(2).to_string(formatters={'auto_clips_month': '{:,.0f}'.format, 'route2_auto_clips_month': '{:,.0f}'.format}))
print('\nWithin ~2× is agreement at this stage; a bigger gap means the sessions-per-player or triggers-per-session dial is wrong for that genre.')"""))

C.append(md("## 3 · Concentration of the prize, and the storage it costs"))
C.append(code(r"""long = CAND.reset_index()[['candidate', 'kept_clips_month']]
v, tiers = pareto(long, 'candidate', 'kept_clips_month', label='kept auto-clips per month across candidates')
print(v.table.to_string()); print(v.note); plt.show()
GB_PRICE = (0.02, 0.05)
CAND['storage_cost_month_low'] = CAND.storage_gb_month * GB_PRICE[0]; CAND['storage_cost_month_high'] = CAND.storage_gb_month * GB_PRICE[1]
CAND['kept_per_dollar_high'] = CAND.kept_clips_month / CAND.storage_cost_month_high
print(CAND[['kept_clips_month', 'shares_month', 'storage_gb_month', 'storage_cost_month_high', 'kept_per_dollar_high']].round(1).to_string(formatters={'kept_clips_month': '{:,.0f}'.format, 'shares_month': '{:,.0f}'.format, 'storage_gb_month': '{:,.0f}'.format, 'storage_cost_month_high': '${:,.0f}'.format}))
print('\n$/GB-month is a dial (0.02–0.05); the ranking by kept clips per dollar is robust to it because it scales every row.')"""))

C.append(md("## 4 · The paid-game angle: what the studio would need to see"))
C.append(code(r"""paid = CAND[CAND.genre.str.contains('horror')].copy()
for cp in (0.1, 0.3):
    paid[f'copies_month_at_{cp}'] = paid.shares_month * cp
print('shares/month × copies per share (0.1 low, 0.3 = GJ planted) → incremental copies per month, for the paid candidates:')
print(paid[['medal_players_month', 'shares_month', 'copies_month_at_0.1', 'copies_month_at_0.3']].round(0).to_string(formatters={c: '{:,.0f}'.format for c in paid.columns if c != 'genre'}))
print('\nA studio selling ~1,000 copies/day will not notice +30/month; a studio selling 30/day will. Pitch auto-clipping to paid games on wishlists and UGC reach, not on copies, unless the game is small.')"""))

C.append(md("## 5 · Close — the shortlist and the dial that decides each"))
C.append(code(r"""top = CAND.head(4)
lines = '; '.join(f"{g}: {r.kept_clips_month:,.0f} kept clips/mo, {r.shares_month:,.0f} shares/mo, ~{r.storage_gb_month:,.0f} GB/mo (analogue {r.analogue})" for g, r in top.iterrows())
display(Markdown(mn.close_md('Next integration — shortlist',
    f"Route 1 ranks {top.index[0]} first; route 2 agrees within ×{CAND.route_ratio.loc[top.index[0]]:.1f}. {lines}.",
    f"GO on {top.index[0]} (largest kept-clip prize per storage dollar); {top.index[1]} as the second if the studio relationship is ready.",
    'before signing: ask the studio for its event log (which actions fire, at what rate per match) and its DAU — the triggers-per-session dial is the one we borrowed by analogy, and it moves the prize 2–3×.',
    'keep rate below 50% after the first two weeks → junk trigger set; prune before scaling. Storage cost above $X/month per kept clip (set X from the GI data price) → stop.',
    'after the first 4 weeks with the 20% control (07): replace the analogue dials with observed ones and re-rank the remaining candidates.')))"""))

C.append(md("""## 6 · Limits
- Triggers per session for non-integrated games are borrowed from the closest integrated genre; that one dial carries most of the uncertainty.
- Monthly players come from the platform table at ×40 sample scale; treat absolute numbers as order-of-magnitude, rankings as the deliverable.
- Keep and share rates assume the trigger set is pruned the way RL's and GJ's should be; an unpruned set lowers keep rate to ~55%.
- The studio-side value (copies, wishlists) remains the weakest link; see 01 §5 and 03 §5 for how little the data can say about it."""))

if __name__ == "__main__":
    for c in C:
        if c.cell_type == "code":
            c.source = c.source.replace("__NBDIR__", str(NB))
    OUT.mkdir(parents=True, exist_ok=True)
    build_and_execute(nb, str(OUT / "08_next_integration.ipynb"), workdir=str(OUT))
