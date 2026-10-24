"""modeling — the /model pipeline: RandomForest + XGBoost, deterministic decisions, house charts.

    res = run_pipeline(df, target='repeat_90d', exclude=['order_id'], entity='retailer_id', time_col='first_order_at')

Decision tree (all printed, none guessed):
    task        bool / 2 distinct values -> binary; <= MAX_CLASSES distinct ints or categorical -> multiclass; else regression
    imbalance   binary/multiclass with minority share < IMBALANCE_SHARE -> class_weight='balanced' (RF), scale_pos_weight (XGB),
                PR-AUC headlines over ROC-AUC, threshold reported at best-F1 as well as 0.5
    split       time_col given -> last TEST_SIZE by time (train on the past, test on the future); else stratified random
    features    numerics as-is; categoricals <= MAX_ONEHOT levels one-hot; higher-cardinality -> frequency encoding; ids/excludes dropped
    models      RF (n_estimators=300) and XGB (300 trees, lr .05, depth 6). No hyper-parameter tuning, ever — this is EDA-grade.
    outputs     metrics table with a naive baseline row, ROC + PR curves (clf) or parity + residuals (reg),
                permutation vs impurity importances (leakage tripwire: one feature > LEAK_SHARE of permutation importance, or a near-perfect score),
                partial dependence for the top-5 numeric features, and a ranked hypothesis list. Exploratory, not causal.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from monaco.viz import BLACK, GRAY, O_DARK, O_MID, titled

MAX_CLASSES = 12
MAX_ONEHOT = 60
IMBALANCE_SHARE = 0.20
TEST_SIZE = 0.25
LEAK_SHARE = 0.50
N_TREES = 300
SEED = 0


# ------------------------------------------------------------------ decisions
def detect_task(y):
    s = y.dropna()
    if s.dtype == bool or s.nunique() == 2:
        return 'binary'
    if isinstance(s.dtype, pd.CategoricalDtype) or s.dtype == object:
        return 'multiclass'
    if np.issubdtype(s.dtype, np.integer) and s.nunique() <= MAX_CLASSES:
        return 'multiclass'
    return 'regression'


def prepare(df, target, exclude=(), features=None, max_onehot=MAX_ONEHOT):
    d = df.dropna(subset=[target]).copy()
    cols = [c for c in (features or d.columns) if c != target and c not in set(exclude)]
    X = pd.DataFrame(index=d.index); log = []; src = {}
    for c in cols:
        s = d[c]
        if np.issubdtype(s.dtype, np.number) or s.dtype == bool:
            X[c] = s.astype(float); log.append((c, 'numeric')); src[c] = c
        elif np.issubdtype(s.dtype, np.datetime64):
            X[c + '_days'] = (s - s.min()).dt.days.astype(float); log.append((c, 'datetime -> days since min')); src[c + '_days'] = c
        elif s.nunique() <= max_onehot:
            dm = pd.get_dummies(s.astype(str), prefix=c, dtype=float); X = pd.concat([X, dm], axis=1); log.append((c, f'one-hot ({dm.shape[1]} levels)'))
            src.update({k: c for k in dm.columns})
        else:
            X[c + '_freq'] = s.map(s.value_counts(normalize=True)).astype(float); log.append((c, f'frequency-encoded ({s.nunique()} levels)')); src[c + '_freq'] = c
    y = d[target]
    return X, y, pd.DataFrame(log, columns=['column', 'treatment']), src


def split(X, y, time=None, test_size=TEST_SIZE, task='binary', seed=SEED):
    from sklearn.model_selection import train_test_split
    if time is not None:
        order = np.argsort(pd.to_datetime(time).values, kind='stable'); cut = int(len(order) * (1 - test_size))
        tr, te = order[:cut], order[cut:]
        return X.iloc[tr], X.iloc[te], y.iloc[tr], y.iloc[te], 'time-based (train = earliest %.0f%%, test = latest %.0f%%)' % (100 * (1 - test_size), 100 * test_size)
    strat = y if task != 'regression' else None
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=test_size, random_state=seed, stratify=strat)
    return Xtr, Xte, ytr, yte, f'random {100*(1-test_size):.0f}/{100*test_size:.0f}' + (' stratified' if strat is not None else '')


# ------------------------------------------------------------------ models
def fit_models(task, Xtr, ytr, imbalanced=False, seed=SEED):
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from xgboost import XGBClassifier, XGBRegressor
    if task == 'regression':
        rf = RandomForestRegressor(n_estimators=N_TREES, min_samples_leaf=5, n_jobs=-1, random_state=seed)
        xg = XGBRegressor(n_estimators=N_TREES, learning_rate=0.05, max_depth=6, subsample=0.9, colsample_bytree=0.9, random_state=seed, n_jobs=-1)
    else:
        rf = RandomForestClassifier(n_estimators=N_TREES, min_samples_leaf=5, n_jobs=-1, random_state=seed, class_weight='balanced' if imbalanced else None)
        kw = {}
        if task == 'binary' and imbalanced:
            pos = (ytr == ytr.value_counts().idxmin()).mean(); kw['scale_pos_weight'] = (1 - pos) / pos
        xg = XGBClassifier(n_estimators=N_TREES, learning_rate=0.05, max_depth=6, subsample=0.9, colsample_bytree=0.9, random_state=seed, n_jobs=-1, eval_metric='logloss', **kw)
    rf.fit(Xtr, ytr); xg.fit(Xtr, ytr)
    return {'RandomForest': rf, 'XGBoost': xg}


# ------------------------------------------------------------------ evaluation
def evaluate(task, models, Xte, yte, ytr, pos_label=None, class_names=None):
    from sklearn import metrics as M
    rows, curves = [], {}
    if task == 'regression':
        base = np.full(len(yte), ytr.mean())
        rows.append(dict(model='baseline (train mean)', MAE=M.mean_absolute_error(yte, base), RMSE=np.sqrt(M.mean_squared_error(yte, base)), R2=M.r2_score(yte, base)))
        for n, m in models.items():
            p = m.predict(Xte); curves[n] = p
            rows.append(dict(model=n, MAE=M.mean_absolute_error(yte, p), RMSE=np.sqrt(M.mean_squared_error(yte, p)), R2=M.r2_score(yte, p)))
    elif task == 'binary':
        classes = sorted(yte.unique()); pos = pos_label if pos_label is not None else classes[-1]
        yb = (yte == pos).astype(int); prev = yb.mean()
        rows.append(dict(model=f'baseline (prevalence {prev:.3f})', ROC_AUC=0.5, PR_AUC=prev, precision_at_0_5=np.nan, recall_at_0_5=np.nan, F1_at_0_5=np.nan, best_F1=np.nan, thr_best_F1=np.nan))
        for n, m in models.items():
            pi = list(m.classes_).index(pos); pr = m.predict_proba(Xte)[:, pi]
            fpr, tpr, _ = M.roc_curve(yb, pr); prec, rec, thr = M.precision_recall_curve(yb, pr)
            f1s = 2 * prec[:-1] * rec[:-1] / np.clip(prec[:-1] + rec[:-1], 1e-9, None); ib = int(np.nanargmax(f1s))
            yhat = (pr >= 0.5).astype(int)
            rows.append(dict(model=n, ROC_AUC=M.roc_auc_score(yb, pr), PR_AUC=M.average_precision_score(yb, pr),
                             precision_at_0_5=M.precision_score(yb, yhat, zero_division=0), recall_at_0_5=M.recall_score(yb, yhat),
                             F1_at_0_5=M.f1_score(yb, yhat), best_F1=f1s[ib], thr_best_F1=thr[ib]))
            curves[n] = dict(fpr=fpr, tpr=tpr, prec=prec, rec=rec, proba=pr, cm=M.confusion_matrix(yb, yhat))
        curves['_prev'] = prev
    else:
        maj = ytr.value_counts().idxmax(); base = np.full(len(yte), maj)
        maj_name = class_names[maj] if class_names is not None else maj
        rows.append(dict(model=f'baseline (majority = {maj_name})', accuracy=M.accuracy_score(yte, base), macro_F1=M.f1_score(yte, base, average='macro'), weighted_F1=M.f1_score(yte, base, average='weighted')))
        for n, m in models.items():
            p = m.predict(Xte)
            rows.append(dict(model=n, accuracy=M.accuracy_score(yte, p), macro_F1=M.f1_score(yte, p, average='macro'), weighted_F1=M.f1_score(yte, p, average='weighted')))
            names = [str(c) for c in class_names] if class_names is not None else None
            curves[n] = dict(report=pd.DataFrame(M.classification_report(yte, p, output_dict=True, zero_division=0, target_names=names)).T.round(3), cm=M.confusion_matrix(yte, p))
    return pd.DataFrame(rows), curves


def plot_curves(task, curves, yte=None):
    if task == 'binary':
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
        cols = {'RandomForest': BLACK, 'XGBoost': O_MID}
        for n, c in curves.items():
            if n.startswith('_'): continue
            axes[0].plot(c['fpr'], c['tpr'], color=cols.get(n, O_DARK), lw=1.8, label=n)
            axes[1].plot(c['rec'], c['prec'], color=cols.get(n, O_DARK), lw=1.8, label=n)
        axes[0].plot([0, 1], [0, 1], color=GRAY, ls='--', lw=1, label='chance'); axes[1].axhline(curves['_prev'], color=GRAY, ls='--', lw=1, label=f'prevalence {curves["_prev"]:.2f}')
        titled(axes[0], 'ROC curve', 'x = false positive rate, y = true positive rate; area = ROC-AUC'); axes[0].set_xlabel('FPR'); axes[0].set_ylabel('TPR')
        titled(axes[1], 'Precision-recall curve', 'the honest curve under imbalance; dashed = a random ranker'); axes[1].set_xlabel('recall'); axes[1].set_ylabel('precision')
        for ax in axes: ax.set_xlim(0, 1); ax.set_ylim(0, 1.02); ax.legend(fontsize=8, loc='lower right' if ax is axes[0] else 'upper right')
        plt.tight_layout(); return fig
    if task == 'regression':
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
        cols = {'RandomForest': BLACK, 'XGBoost': O_MID}
        lo, hi = float(np.min(yte)), float(np.max(yte))
        for n, p in curves.items():
            axes[0].scatter(yte, p, s=6, alpha=.35, color=cols.get(n, O_DARK), label=n)
            axes[1].scatter(p, yte - p, s=6, alpha=.35, color=cols.get(n, O_DARK), label=n)
        axes[0].plot([lo, hi], [lo, hi], color=GRAY, ls='--', lw=1); axes[1].axhline(0, color=GRAY, ls='--', lw=1)
        titled(axes[0], 'Parity: predicted vs actual (test)', 'points on the dashed line are perfect predictions'); axes[0].set_xlabel('actual'); axes[0].set_ylabel('predicted')
        titled(axes[1], 'Residuals vs predicted (test)', 'a fan or a curve here means the model is missing structure'); axes[1].set_xlabel('predicted'); axes[1].set_ylabel('actual − predicted')
        for ax in axes: ax.legend(fontsize=8)
        plt.tight_layout(); return fig
    return None


# ------------------------------------------------------------------ importances & PDP
def importances(models, Xte, yte, task, src=None, n_repeats=5, top=15, seed=SEED):
    """Permutation (test) and impurity (train) importances, AGGREGATED to source columns (one-hot dummies
    and encodings summed back to the column they came from), normalized to shares."""
    from sklearn.inspection import permutation_importance
    scoring = 'r2' if task == 'regression' else ('roc_auc' if task == 'binary' else 'f1_macro')
    src = src or {c: c for c in Xte.columns}
    tabs = {}
    for n, m in models.items():
        imp = pd.Series(m.feature_importances_, index=Xte.columns, name='impurity')
        pi = permutation_importance(m, Xte, yte, n_repeats=n_repeats, random_state=seed, scoring=scoring, n_jobs=-1)
        perm = pd.Series(pi.importances_mean, index=Xte.columns, name='permutation').clip(lower=0)
        t = pd.concat([imp, perm], axis=1); t['source'] = [src.get(c, c) for c in t.index]
        t = t.groupby('source').sum()
        tabs[n] = t / t.sum().replace(0, 1e-12)
    # consensus rank: mean of normalized permutation importance across models
    cons = pd.concat([t.permutation.rename(n) for n, t in tabs.items()], axis=1)
    cons['consensus'] = cons.mean(axis=1); cons = cons.sort_values('consensus', ascending=False)
    leak = [(n, t.permutation.idxmax(), t.permutation.max()) for n, t in tabs.items() if t.permutation.max() > LEAK_SHARE]   # permutation, not impurity: impurity over-credits high-cardinality columns
    n_rows = min(top, max(len(t) for t in tabs.values()))
    fig, axes = plt.subplots(1, len(tabs), figsize=(6 * len(tabs), 0.42 * n_rows + 2.4), squeeze=False); axes = axes[0]
    for ax, (n, t) in zip(axes, tabs.items()):
        tt = t.sort_values('permutation', ascending=False).head(top)[::-1]
        y = np.arange(len(tt)); h = 0.38
        ax.barh(y + h / 2, tt.permutation, height=h, color=BLACK, label='permutation (test)')
        ax.barh(y - h / 2, tt.impurity, height=h, color=O_MID, label='impurity (train)')
        for yi, (pv, iv) in enumerate(zip(tt.permutation, tt.impurity)):
            ax.text(pv + 0.003, yi + h / 2, f'{100*pv:.0f}%', va='center', fontsize=7.5); ax.text(iv + 0.003, yi - h / 2, f'{100*iv:.0f}%', va='center', fontsize=7.5, color='#666')
        ax.set_yticks(y); ax.set_yticklabels(tt.index, fontsize=8); ax.set_xlim(0, max(tt.max().max() * 1.25, 0.05))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{100*v:.0f}%')); ax.grid(axis='x', color='#e6e6e6'); ax.grid(axis='y', visible=False)
        titled(ax, f'{n}: feature importance (top {top}, by source column)', f'share of total; permutation = drop in {scoring} when shuffled on test; one-hot levels summed', pad=26)
        ax.legend(fontsize=8, loc='lower right')
    plt.tight_layout()
    return cons, tabs, leak, fig


def pdp(model, X, features, task, grid=20):
    from sklearn.inspection import partial_dependence
    feats = [f for f in features if X[f].nunique() > 2][:5]
    if not feats: return None
    fig, axes = plt.subplots(1, len(feats), figsize=(3.6 * len(feats), 3.4), squeeze=False); axes = axes[0]
    for ax, f in zip(axes, feats):
        pd_ = partial_dependence(model, X, [f], grid_resolution=grid, kind='average')
        xs, ys = pd_['grid_values'][0], pd_['average'][0]
        ax.plot(xs, ys, color=O_MID, lw=2); ax.set_xlabel(f); ax.grid(axis='y', color='#e6e6e6')
        ax.set_title(f, loc='left', fontsize=9.5, fontweight='bold')
    axes[0].set_ylabel('partial dependence' + (' (P[positive])' if task == 'binary' else ''))
    fig.suptitle('Partial dependence — top numeric features (exploratory, not causal)', x=0.01, ha='left', fontsize=10.8, fontweight='bold')
    plt.tight_layout(rect=(0, 0, 1, 0.93))
    return fig


# ------------------------------------------------------------------ the pipeline
def run_pipeline(df, target, exclude=(), features=None, entity=None, time_col=None, task=None, test_size=TEST_SIZE, seed=SEED, pos_label=None, label=None):
    """Runs everything, prints the decisions, returns a dict of results and figures. See module docstring."""
    d = df.copy()
    if entity is not None and entity in d.columns and d[entity].duplicated().any():
        print(f'NOTE: {entity} is not unique per row — modelling at ROW grain; aggregate first if you want one row per {entity}.')
    task = task or detect_task(d[target])
    ex = list(exclude) + ([entity] if entity else []) + ([time_col] if time_col else [])
    X, y, treat, src = prepare(d, target, ex, features)
    print(f'target = {target!r} ({label or task}); task -> {task}; n = {len(y):,}; features -> {X.shape[1]} columns from {len(treat)} inputs')
    print(treat.to_string(index=False))
    imbalanced = False; class_names = None
    if task != 'regression':
        vc = y.value_counts(normalize=True)
        thr = IMBALANCE_SHARE if task == 'binary' else 0.5 / y.nunique()          # multiclass: a class under half its uniform share
        imbalanced = vc.min() < thr
        print(f'class balance: {vc.round(3).to_dict()} -> {"IMBALANCED (a class < %.0f%%): balanced class weights, %s" % (100*thr, "PR-AUC headlines" if task == "binary" else "macro-F1 headlines") if imbalanced else "balanced enough: default weights"}')
        class_names = sorted(y.unique(), key=str)                                  # XGBoost needs 0..k-1 integer labels
        if pos_label is not None: pos_label = class_names.index(pos_label)
        elif task == 'binary': pos_label = len(class_names) - 1
        y = y.map({c: i for i, c in enumerate(class_names)}).astype(int)
        print('label encoding:', {i: c for i, c in enumerate(class_names)})
    Xtr, Xte, ytr, yte, how = split(X, y, d.loc[X.index, time_col] if time_col else None, test_size, task, seed)
    print(f'split: {how}; train {len(Xtr):,} / test {len(Xte):,}')
    models = fit_models(task, Xtr, ytr, imbalanced, seed)
    metrics, curves = evaluate(task, models, Xte, yte, ytr, pos_label, class_names)
    print(); print(metrics.round(4).to_string(index=False))
    figs = {'curves': plot_curves(task, curves, yte)}
    cons, tabs, leak, figs['importance'] = importances(models, Xte, yte, task, src=src, seed=seed)
    print(); print('consensus importance (mean normalized permutation importance across models), top 10:'); print(cons.head(10).round(4).to_string())
    for n, f, v in leak:
        print(f'LEAKAGE TRIPWIRE: {n} puts {100*v:.0f}% of permutation importance on {f!r} — check whether it is defined from the target.')
    best = metrics.iloc[1:]
    too_good = (task == 'regression' and best.R2.max() > 0.98) or (task == 'binary' and best.ROC_AUC.max() > 0.98) or (task == 'multiclass' and best.macro_F1.max() > 0.98)
    if too_good:
        leak.append(('score', 'suspiciously good', float(best.R2.max() if task == 'regression' else (best.ROC_AUC.max() if task == 'binary' else best.macro_F1.max()))))
        print('LEAKAGE TRIPWIRE: near-perfect test score — a feature is probably defined from the target (or the task is trivial). Say which before quoting.')
    top = [f for f in cons.index if f in X.columns]           # PDP only for raw numeric columns
    figs['pdp'] = pdp(models['XGBoost'], Xte, top, task)
    plt.close('all')                                           # figures are returned in figs and displayed by the notebook, once
    return dict(task=task, imbalanced=imbalanced, split=how, class_names=class_names, X=X, y=y, Xtr=Xtr, Xte=Xte, ytr=ytr, yte=yte, models=models,
                metrics=metrics, curves=curves, importances=cons, importance_tables=tabs, leak=leak, treatment=treat, figs=figs)


def hypotheses(res, k=5):
    """Ranked hypothesis list from the consensus importances — exploratory, not causal."""
    top = res['importances'].head(k)
    lines = [f'H{i+1}: {f} is associated with the target (consensus importance {100*v:.0f}%) — check direction on the PDP, then test it as a segment cut in the deep-dive notebook.'
             for i, (f, v) in enumerate(top.consensus.items())]
    return lines
