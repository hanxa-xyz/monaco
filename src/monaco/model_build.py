"""model_build — turn a SPEC into one executed modelling notebook (RF + XGB, decisions printed).

    from model_build import build_model_notebook
    build_model_notebook(SPEC, '<company>/notebooks/model.ipynb')

SPEC keys:
    company, title      header strings
    setup_code          python defining `df`
    derive_code         optional; derived columns / feature generation
    entity              entity column (dropped from features; warns if rows are not unique per entity)
    time_col            optional; enables the time-based split and is dropped from features
    exclude             columns never used as features (ids, free text, anything defined from a target)
    targets             [dict(col='y', label='...', exclude=[...extra per-target...], task=None|'binary'|'multiclass'|'regression', pos_label=None), ...]
    toolkit_rel         optional; only for a checkout where monaco is not pip-installed
One section per target: decisions → metrics → curves → importances (+ leakage tripwire) → PDP → hypothesis list.
"""
import os

from monaco.viz import build_and_execute, code, md, new_notebook


def build_model_notebook(spec, out_path, workdir=None):
    S = dict(spec)
    nb = new_notebook(); C = nb.cells
    C.append(md(f"# {S.get('company', '<company>')} — modelling pass (RF + XGBoost)\n{S.get('title', '')}\n\n"
                "Deterministic decisions, printed: task type from the target · imbalance from class shares · split (time-based if a "
                "time column exists) · feature treatment per column. Two models with default-grade settings, **no tuning**. "
                "Everything here is **exploratory, not causal** — importances rank hypotheses, they do not size recommendations."))
    C.append(md("## 0 · Setup"))
    C.append(code("import warnings; warnings.filterwarnings('ignore')\nimport sys, os\n"
                  + (f"sys.path.insert(0, os.path.abspath({repr(S['toolkit_rel'])}))\n" if S.get('toolkit_rel') else "") +
                  "import pandas as pd, numpy as np\nimport matplotlib.pyplot as plt\n"
                  "from monaco.viz import apply_style\nfrom monaco.modeling import run_pipeline, hypotheses\n"
                  "apply_style(dpi=110); pd.set_option('display.width', 220)\n\n" + S['setup_code'].strip() +
                  ("\n\n# --- derived columns / features ---\n" + S['derive_code'].strip() if S.get('derive_code') else '') +
                  "\nprint('df:', df.shape)"))
    ex_g = list(S.get('exclude', []))
    for i, t in enumerate(S['targets'], 1):
        col = t['col']; ex = ex_g + list(t.get('exclude', []))
        C.append(md(f"## {i} · target `{col}` — {t.get('label', '')}\n"
                    "Decisions are printed first (task, features, balance, split); then the metrics table with a naive baseline row."))
        C.append(code(f"res_{i} = run_pipeline(df, {repr(col)}, exclude={repr(ex)}, entity={repr(S.get('entity'))}, time_col={repr(S.get('time_col'))}, "
                      f"task={repr(t.get('task'))}, pos_label={repr(t.get('pos_label'))}, label={repr(t.get('label'))})"))
        C.append(md(f"### {i}.1 · Curves\nClassification: ROC + precision-recall (PR is the honest one under imbalance). Regression: parity + residuals."))
        C.append(code(f"f = res_{i}['figs']['curves']\nif f is not None: display(f)\nplt.close('all')\n"
                      f"if res_{i}['task'] == 'binary':\n    for n, c in res_{i}['curves'].items():\n        if not n.startswith('_'): print(n, 'confusion @0.5 [[TN FP][FN TP]]:', c['cm'].tolist())\n"
                      f"elif res_{i}['task'] == 'multiclass':\n    for n, c in res_{i}['curves'].items(): print(n); print(c['report'].to_string())"))
        C.append(md(f"### {i}.2 · Importances + leakage tripwire\nPermutation (test-set, black) vs impurity (train, orange), normalized to shares. "
                    "If the two disagree strongly, trust permutation. A single feature holding more than half the permutation importance, or a near-perfect test score, is flagged — check it isn't defined from the target."))
        C.append(code(f"display(res_{i}['figs']['importance']); plt.close('all')\n"
                      f"print(res_{i}['importances'].head(15).round(4).to_string())\n"
                      f"print('leakage flags:', res_{i}['leak'] or 'none')"))
        C.append(md(f"### {i}.3 · Partial dependence (top numeric features) and the hypothesis list"))
        C.append(code(f"f = res_{i}['figs']['pdp']\nif f is not None: display(f)\nplt.close('all')\n"
                      f"for h in hypotheses(res_{i}): print(h)"))
    C.append(md("## Stop condition\nMetrics with a baseline, curves, importances with the tripwire, PDPs, and a ranked hypothesis list per target. "
                "No tuning, no stacking, no feature engineering beyond `derive_code`. Hypotheses go to the deep-dive notebook; sizing goes to `/takehome-sizing`."))
    build_and_execute(nb, out_path, workdir=workdir or os.path.dirname(os.path.abspath(out_path)))
