"""eda_build — turn a SPEC dict into one executed EDA notebook, one section per view, in the fixed order.

    from eda_build import build_from_spec
    build_from_spec(SPEC, '<company>/notebooks/eda_views.ipynb')

SPEC keys (only `setup_code`, `entity_label`, `metric` and `dims` are needed for the core views;
everything else is optional and its view auto-skips when absent):

    company, title           strings for the header
    setup_code               python that defines `df` (and optionally TABLES = {'name': DataFrame} for structure)
    derive_code              python run after setup: derived columns (bands, flags, tiers)
    entity                   column identifying one entity (None -> one row = one entity)
    entity_label             'offer', 'retailer', ...
    keys                     {'df': [['col', ...], ...]} candidate keys to test for grain
    metric, metric_label     the ONE anchor metric and its human label
    dims                     <= 3 dimension columns (categorical / banded)
    flag, flag_label         a 0/1 column for penetration
    mix                      [(dim, by), ...] pairs for the mix view
    time                     dict(col=..., freq='M', split=None) or None
    saturation               [dict(entity=..., count_col=None, label=...), ...]
    pareto                   [dict(entity=..., value=..., label=...), ...]
    views                    subset/order of ['structure','trio','penetration','mix','distribution','time','saturation','pareto']
    toolkit_rel              optional; only for a checkout where monaco is not pip-installed

Guardrail: this renders ONE chart per (view, dimension) — never a metric x dim x view cross-product.
If you want more, add a dimension to the spec deliberately.
"""
import os

from monaco.viz import build_and_execute, code, md, new_notebook

ALL_VIEWS = ['structure', 'trio', 'penetration', 'mix', 'distribution', 'time', 'saturation', 'pareto']

WHAT = {
    'structure': 'one row = ? shape, dtypes, nulls, dupes, describe, granularity verdicts. Tables only.',
    'trio': 'by each dimension: total metric · metric per entity · N. Three horizontal panels, same row order.',
    'penetration': 'of each group, what % has the flag. Horizontal bars, overall rate as reference. Rates within group — bars do not sum to 100%.',
    'mix': 'within each group of D1, how D2 splits. 100%-stacked horizontal bars.',
    'distribution': 'of the total, how it splits across the dimension. Vertical bars; each series sums to 100%.',
    'time': 'metric by period, optionally split by one dimension. Line, true date axis.',
    'saturation': 'cumulative % of entities with <= k of X; the k needed to reach 80/90/95%. Step CDF.',
    'pareto': 'cumulative share of value vs share of entities; the smallest set producing 50/80%. Lorenz curve.',
}


def _show(call, extra=''):
    return f"v = {call}\nprint(v.table.to_string())\nprint()\nprint(v.note){extra}\nplt.show()"


def build_from_spec(spec, out_path, workdir=None):
    S = dict(spec)
    views = S.get('views') or ALL_VIEWS
    ent = S.get('entity'); ent_r = repr(ent)
    el = repr(S.get('entity_label', ent or 'rows'))
    metric, ml = S.get('metric'), repr(S.get('metric_label', S.get('metric')))
    dims = S.get('dims', [])
    nb = new_notebook(); C = nb.cells
    C.append(md(f"# {S.get('company', '<company>')} — EDA views\n{S.get('title', '')}\n\n"
                "Fixed vocabulary, one chart per (view, dimension), every table printed. Sections: "
                + ' → '.join(f'**{v}**' for v in views) + '.'))
    C.append(md("## 0 · Setup"))
    C.append(code("import warnings; warnings.filterwarnings('ignore')\nimport sys, os\n"
                  + (f"sys.path.insert(0, os.path.abspath({repr(S['toolkit_rel'])}))\n" if S.get('toolkit_rel') else "") +
                  "import pandas as pd, numpy as np\nimport matplotlib.pyplot as plt\n"
                  "from monaco.viz import apply_style\nfrom monaco.eda import structure, trio, penetration, mix, distribution, time_series, saturation, pareto\n"
                  "apply_style(dpi=110); pd.set_option('display.width', 220)\n\n" + S['setup_code'].strip() +
                  ("\n\n# --- derived columns ---\n" + S['derive_code'].strip() if S.get('derive_code') else '') +
                  "\nprint('df:', df.shape)"))
    n = 0
    for v in views:
        n += 1
        C.append(md(f"## {n} · {v}\n{WHAT[v]}"))
        if v == 'structure':
            tabs = "TABLES if 'TABLES' in dir() else {'df': df}"
            C.append(code(_show(f"structure({tabs}, keys={repr(S.get('keys', {}))})").replace('print(v.table.to_string())\n', '')))
        elif v == 'trio':
            if not (metric and dims):
                C.append(md("_skipped: needs `metric` and `dims` in the spec._")); continue
            for d in dims:
                C.append(code(_show(f"trio(df, {repr(d)}, {repr(metric)}, entity={ent_r}, metric_label={ml}, entity_label={el})")))
        elif v == 'penetration':
            if not (S.get('flag') and dims):
                C.append(md("_skipped: no `flag` (0/1 column) in the spec._")); continue
            for d in dims:
                C.append(code(_show(f"penetration(df, {repr(d)}, {repr(S['flag'])}, flag_label={repr(S.get('flag_label', S['flag']))}, entity={ent_r})")))
        elif v == 'mix':
            if not S.get('mix'):
                C.append(md("_skipped: no `mix` pairs in the spec._")); continue
            for d, b in S['mix']:
                C.append(code(_show(f"mix(df, {repr(d)}, {repr(b)}, entity={ent_r})")))
        elif v == 'distribution':
            if not dims:
                C.append(md("_skipped: no `dims`._")); continue
            for d in dims:
                C.append(code(_show(f"distribution(df, {repr(d)}, metric={repr(metric)}, entity={ent_r}, metric_label={ml}, entity_label={el})")))
        elif v == 'time':
            t = S.get('time')
            if not t:
                C.append(md("_skipped: no time column in the spec (the data has no time dimension)._")); continue
            C.append(code(_show(f"time_series(df, {repr(t['col'])}, metric={repr(metric)}, freq={repr(t.get('freq', 'M'))}, split={repr(t.get('split'))}, metric_label={ml}, entity={ent_r})")))
        elif v == 'saturation':
            if not S.get('saturation'):
                C.append(md("_skipped: no `saturation` entries in the spec._")); continue
            for s in S['saturation']:
                C.append(code(f"v, ks = saturation(df, {repr(s['entity'])}, count_col={repr(s.get('count_col'))}, label={repr(s.get('label'))})\n"
                              "print(v.table.to_string()); print(); print('k needed:', ks); print(v.note)\nplt.show()"))
        elif v == 'pareto':
            if not S.get('pareto'):
                C.append(md("_skipped: no `pareto` entries in the spec._")); continue
            for p in S['pareto']:
                C.append(code(f"v, tiers = pareto(df, {repr(p['entity'])}, {repr(p['value'])}, label={repr(p.get('label'))})\n"
                              "print(v.table.to_string()); print(); print(v.note)\nplt.show()"))
    C.append(md("## Stop condition\nEvery requested view rendered once per dimension. Do not add views or dimensions here — "
                "hypotheses go to the deep-dive notebooks; this notebook is the map, not the argument."))
    build_and_execute(nb, out_path, workdir=workdir or os.path.dirname(os.path.abspath(out_path)))
