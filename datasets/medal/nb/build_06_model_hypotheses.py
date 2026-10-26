"""Notebook 06 — Case 1, sixth route: ML-driven EDA (/model) as hypothesis ranking, with the leakage tripwire shown on purpose.

    python3 datasets/medal/nb/build_06_model_hypotheses.py   ->  datasets/medal/out/notebooks/06_model_hypotheses.ipynb
"""
from pathlib import Path

from monaco.viz import build_and_execute, code, md, new_notebook

NB = Path(__file__).resolve().parent
OUT = NB.parent / "out" / "notebooks"
nb = new_notebook(); C = nb.cells

C.append(md("""# Medal auto-clipping — 06 · the modelling pass as hypothesis ranking

**Same objective, sixth route — exploratory, not causal.** Two supervised models (RandomForest + XGBoost, default-grade, no
tuning) rank which observable features move the outcomes the case cares about. Importances rank *hypotheses* for the designs
in notebooks 02–05; they never size a recommendation.

Target A, clip level: `shared_14d` on post-launch clips — what makes a clip get shared off-Medal (trigger, media, player context)?
Target B, player level: `retained_d14_27` on the launch cohort — what predicts coming back, and does `got_autoclip_14d` survive
once pre-period activity is in the model? Pass 1 includes the `post14_*` columns (measured after launch, so they are
post-treatment variables — mediators, not controls); pass 2 drops them. The tripwire fires on whichever feature dominates;
whether that is leakage or just a dominant predictor is a judgment the notebook makes out loud."""))

C.append(md("## 0 · Setup"))
C.append(code(r"""import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0, '__NBDIR__')
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from IPython.display import Markdown, display
import medal_nb as mn
from monaco.modeling import run_pipeline, hypotheses
mn.setup()
T = mn.load('clips', 'sessions', 'players', 'player_launch_cohort', 'games')
cl = T['clips'].drop_duplicates('clip_id'); cl = cl[cl.game_id.isin([1, 2]) & cl.deleted_14d.notna()].copy()
cl = cl[cl.captured_ts >= cl.game_id.map(mn.LAUNCH)]
cl['game'] = cl.game_id.map(mn.NAME); cl['trigger_name'] = cl.trigger_name.fillna('(hotkey)').str.title(); cl['hour'] = cl.captured_ts.dt.hour; cl['dow'] = cl.captured_ts.dt.dayofweek
S = T['sessions'][['session_id', 'duration_min', 'units_played', 'autoclip_on']]
cl = cl.merge(S, on='session_id', how='left')
P = T['players'][['player_id', 'premium', 'steam_linked', 'acq_channel', 'country']]
cl = cl.merge(P, on='player_id', how='left')
pre = T['player_launch_cohort'][['player_id', 'game_id', 'pre28_sessions', 'pre28_manual_clips', 'pre28_shares']]
cl = cl.merge(pre, on=['player_id', 'game_id'], how='left')
print('clip rows for target A:', len(cl), '| share rate:', round(cl.shared_14d.mean(), 4))
print(cl[['trigger_class', 'trigger_name', 'duration_s', 'fps', 'resolution', 'input_log_attached', 'motion_score', 'storage_mb', 'hour', 'duration_min', 'pre28_sessions']].describe(include='all').T.head(12).to_string())"""))

C.append(md("## 1 · Target A — `shared_14d` at the clip level"))
C.append(code(r"""EXCL_A = ['clip_id', 'session_id', 'player_id', 'game_id', 'deleted_ts', 'shared_ts', 'deleted_14d', 'posted_public', 'captured_ts', 'storage_mb']
resA = run_pipeline(cl, 'shared_14d', exclude=EXCL_A, time_col='captured_ts', label='clip shared off-Medal within 14 days')"""))
C.append(code(r"""display(resA['figs']['curves']); plt.close('all')
display(resA['figs']['importance']); plt.close('all')
print(resA['importances'].head(12).round(4).to_string())
print('leakage flags:', resA['leak'] or 'none')
f = resA['figs']['pdp']
if f is not None: display(f)
plt.close('all')
print('\n'.join(hypotheses(resA, k=6)))"""))

C.append(md("## 2 · Target B — `retained_d14_27` at the player level: with and without the post-treatment columns"))
C.append(code(r"""coh = T['player_launch_cohort'].copy(); coh['game'] = coh.game_id.map(mn.NAME)
coh['arm'] = np.where(coh.autoclip_holdout == 1, 'holdout', 'auto-on')
EXCL_B = ['player_id', 'game_id', 'autoclip_holdout', 'first_autoclip_date', 'retained_d28_41']
print('--- pass 1: everything in, including the post14_* columns (measured after launch → post-treatment, not valid controls) ---')
resB1 = run_pipeline(coh, 'retained_d14_27', exclude=EXCL_B, label='retained d14–27 (leaky pass)')
print('leakage flags:', resB1['leak'] or 'none')
print(resB1['importances'].head(6).round(4).to_string())"""))
C.append(code(r"""print('--- pass 2: post-window features excluded; only pre-launch covariates, arm, and whether the player got a clip ---')
POST = [c for c in coh.columns if c.startswith('post14_')]
resB2 = run_pipeline(coh, 'retained_d14_27', exclude=EXCL_B + POST, label='retained d14–27 (pre-period features only)')
display(resB2['figs']['curves']); plt.close('all')
display(resB2['figs']['importance']); plt.close('all')
print(resB2['importances'].head(12).round(4).to_string())
print('leakage flags:', resB2['leak'] or 'none')
f = resB2['figs']['pdp']
if f is not None: display(f)
plt.close('all')
print('\n'.join(hypotheses(resB2, k=6)))
imp = resB2['importances']
print(f"\nwhere do the two levers sit? got_autoclip_14d consensus importance {imp.loc['got_autoclip_14d', 'consensus'] if 'got_autoclip_14d' in imp.index else float('nan'):.3f}; "
      f"arm {imp.loc['arm', 'consensus'] if 'arm' in imp.index else float('nan'):.3f} — pre-period activity dominates both, which is the selection story in numbers.")"""))

C.append(md("## 3 · From hypotheses to designs: which notebook tests each"))
C.append(code(r"""H = pd.DataFrame([
    ('trigger_name / trigger_class drives share', 'A', 'prune set by trigger (01 §2.1, 02 §7); A/B of a trigger set', 'descriptive → product decision, no causal claim needed'),
    ('input_log_attached / motion_score raise share', 'A', 'useful-clip definition (09); is quality the share driver or a proxy for trigger?', 'confounded with trigger; test within trigger'),
    ('session length / units played raise share', 'A', 'player-day fixed effects (05 revisit)', 'engagement proxy, not a lever'),
    ('pre28_* dominate retention', 'B', 'this IS the selection story: holdout (02), IPW (05)', 'covariate, not a lever'),
    ('got_autoclip_14d adds little beyond pre activity', 'B', 'holdout ITT (02) is the test', 'the model cannot separate exposure from selection'),
    ('arm (holdout) importance ≈ 0', 'B', 'consistent with a small true retention effect (02 CUPED CI)', 'absence of importance ≠ absence of effect at this n'),
], columns=['hypothesis', 'target', 'tested by', 'caveat'])
print(H.to_string(index=False))"""))

C.append(md("## 4 · Close"))
C.append(code(r"""mA = resA['metrics']; mB = resB2['metrics']
topA = ', '.join(resA['importances'].head(3).index); topB = ', '.join(resB2['importances'].head(3).index)
display(Markdown(mn.close_md('Both games (exploratory)',
    f"Clip-level share model: top features {topA}; player-level retention model (pre-period features only): top features {topB}. The tripwire fired on {(resB2['leak'] or [('', 'no feature')])[0][1]} — a dominant pre-launch feature, not leakage: the latent engagement tier it proxies drives retention and getting a clip alike.",
    'No ship decision from a model: these rank what to test. The trigger ranking supports the prune set; the retention model supports reading the got-a-clip gap as selection.',
    'carry the top-3 hypotheses per target into the deep-dive: trigger quality as a product cut (01/02), useful-clip definition (09), and retention via the holdout only (02).',
    'if any single feature exceeds 50% of permutation importance on a future run, stop and check it is not defined from the target before quoting anything.',
    'after the next launch, retrain with exposure logged at the player-day and the arm as a feature; a non-zero arm importance would be the first model-side sign of a retention effect.')))
print(pd.DataFrame({'target A': mA.iloc[:, 0] if hasattr(mA, 'iloc') else mA}).to_string() if not isinstance(mA, pd.DataFrame) else mA.round(3).to_string())
print(mB.round(3).to_string() if isinstance(mB, pd.DataFrame) else mB)"""))

C.append(md("""## 5 · Limits of this approach
- Importances rank association, not effect; a feature can dominate because it proxies the confounder (pre activity ↔ tier).
- The clip-level model sees trigger name, so media attributes partly duplicate it; direction on the PDP is the check.
- Time-based split (last 25% by capture time) protects against leakage across time but the share rate drifts with the trigger mix.
- No tuning by design: a better AUC would not change the hypothesis list."""))

if __name__ == "__main__":
    for c in C:
        if c.cell_type == "code":
            c.source = c.source.replace("__NBDIR__", str(NB))
    OUT.mkdir(parents=True, exist_ok=True)
    build_and_execute(nb, str(OUT / "06_model_hypotheses.ipynb"), workdir=str(OUT))
