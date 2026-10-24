"""eda_views — the fixed EDA view vocabulary. One function per view, house grammar baked in.

Every /eda-<view> skill calls exactly one of these; the /eda orchestrator renders them in order from a
SPEC dict (see monaco.eda_build). Keeping the vocabulary strict is what keeps the charts mechanical:

    structure     one row = ? shape, dtypes, nulls, dupes, describe, granularity     tables only
    trio          by dimension: total metric · metric per entity · N               3 HORIZONTAL panels
    penetration   of each group, what % has flag F                                 HORIZONTAL bars
    mix           within each group of D1, how does D2 split                       100%-stacked HORIZONTAL
    distribution  of the total (entities, and metric), how it splits across D      VERTICAL bars
    time          metric by period, optionally split by one dim                    LINE, true date axis
    saturation    cumulative % of entities with <= k of X; k to reach 80/90/95%    STEP CDF
    pareto        cumulative % of value vs % of entities; smallest set making 80%   LORENZ curve

Every function returns View(fig, table, note): the figure (or None), the underlying table (always
print it in the notebook — auditable without a re-run), and a default 'How to read' note.
Rules honoured everywhere: titled(); direct value label on every bar; n= in tick labels; top-K + 'Else'
on categoricals; cells with n < MIN_CELL_N drawn pale with grey tick text; one hue + black; GRAY = reference.
"""
from collections import namedtuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from monaco.viz import BLACK, GRAY, MIN_CELL_N, O_DARK, O_LIGHT, O_MID, O_PALE, titled

View = namedtuple('View', 'fig table note')
TOP_K = 6
ELSE = 'Else'
MUTED_TXT = '#9a9a9a'


# ------------------------------------------------------------------ helpers
def _num(v):
    return f'{v:,.0f}' if abs(v) >= 100 else f'{v:,.1f}'


def _pct(v):
    return f'{100*v:.0f}%' if v >= 0.10 or v == 0 else f'{100*v:.1f}%'


def _axis_num(v, _=None):
    a = abs(v)
    return f'{v/1e6:.1f}M' if a >= 1e6 else (f'{v/1e3:.0f}k' if a >= 1e4 else f'{v:,.0f}')


def topk(s, k=TOP_K, else_label=ELSE):
    """Collapse a categorical Series to its top-k values + 'Else' (100% coverage). Ordered categoricals
    with <= k+2 levels are kept whole so bands stay in order."""
    if s.nunique() <= k + 3:                       # small categoricals stay whole: an 'Else' of 3 levels hides more than it helps
        return s.astype(str)
    keep = s.value_counts().index[:k]
    out = s.astype(str).where(s.isin(keep), else_label)
    return out


def _bar_labels(ax, bars, labels, horizontal=True, muted=None, inside=False):
    for i, (b, lab) in enumerate(zip(bars, labels)):
        col = MUTED_TXT if (muted is not None and muted[i]) else '#1a1a1a'
        if horizontal:
            w = b.get_width()
            ax.text(w + (0 if inside else ax.get_xlim()[1] * 0.01), b.get_y() + b.get_height() / 2, lab,
                    va='center', ha='left', fontsize=8.5, color=col)
        else:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, h + ax.get_ylim()[1] * 0.01, lab,
                    va='bottom', ha='center', fontsize=8.5, color=col)


def _mute_ticks(ax, muted, axis='y'):
    ticks = ax.get_yticklabels() if axis == 'y' else ax.get_xticklabels()
    for t, m in zip(ticks, muted):
        if m:
            t.set_color(MUTED_TXT)


# ------------------------------------------------------------------ 1 structure
def structure(tables, keys=None, percentiles=(.25, .5, .75, .99), max_cat_levels=12):
    """tables: {name: DataFrame}. keys: {name: [[col,...], ...]} candidate key sets to test for grain.
    Prints shape/dtypes/nulls/dupes/describe/value_counts per table and the granularity verdicts.
    Returns View(None, dict-of-tables, note)."""
    out = {}
    for name, df in tables.items():
        print(f'=== {name}: {len(df):,} rows x {df.shape[1]} cols, {df.memory_usage(deep=True).sum()/1e6:.1f} MB')
        prof = pd.DataFrame({'dtype': df.dtypes.astype(str), 'nulls': df.isna().sum(),
                             'null_%': (df.isna().mean() * 100).round(1), 'distinct': df.nunique()})
        print(prof.to_string()); out[f'{name}_profile'] = prof
        print(f'duplicate rows: {df.duplicated().sum():,}')
        for ks in (keys or {}).get(name, []):
            n_key = len(df.drop_duplicates(ks)); grain = 'IS the grain' if n_key == len(df) else f'NOT the grain ({len(df)-n_key:,} rows share a key)'
            print(f'key {ks}: {n_key:,} distinct of {len(df):,} rows -> {grain}')
        num = df.select_dtypes('number')
        if not num.empty:
            desc = num.describe(percentiles=list(percentiles)).T.round(2)
            print(desc.to_string()); out[f'{name}_describe'] = desc
        for c in df.select_dtypes(exclude='number').columns:
            vc = df[c].value_counts(dropna=False)
            if len(vc) <= max_cat_levels:
                print(f'-- {c}: ' + ', '.join(f'{k}={v:,} ({100*v/len(df):.0f}%)' for k, v in vc.items()))
            else:
                print(f'-- {c}: {len(vc):,} levels; top: ' + ', '.join(f'{k}={v:,}' for k, v in vc.head(5).items()))
        print()
    return View(None, out, 'Read the grain verdicts first: every count downstream depends on knowing what one row is.')


# ------------------------------------------------------------------ 2 trio
def trio(df, dim, metric, entity=None, top_k=TOP_K, metric_label=None, entity_label=None, fmt=_num):
    """By `dim`: total metric · metric per entity · N entities. Three horizontal panels sharing row order
    (sorted by total). If `entity` is None, one row = one entity."""
    d = df.assign(_g=topk(df[dim], top_k))
    if entity is not None:
        per = d.groupby(['_g', entity], observed=True)[metric].sum().reset_index()
        g = per.groupby('_g', observed=True)[metric].agg(total='sum', per_entity='mean', n='count')
    else:
        g = d.groupby('_g', observed=True)[metric].agg(total='sum', per_entity='mean', n='count')
    g = g.sort_values('total', ascending=True)          # ascending so the largest is at the top of a barh
    g['share_of_total'] = g.total / g.total.sum()
    muted = (g.n < MIN_CELL_N).values
    ml, el = metric_label or metric, entity_label or (entity or 'rows')
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 0.45 * len(g) + 2.2), sharey=True, squeeze=False)
    axes = axes[0]
    y = np.arange(len(g)); ticks = [f'{i} (n={n:,})' for i, n in zip(g.index, g.n)]
    specs = [('total', f'total {ml}', BLACK, [f'{fmt(v)} ({_pct(s)})' for v, s in zip(g.total, g.share_of_total)]),
             ('per_entity', f'{ml} per {el}', O_MID, [fmt(v) for v in g.per_entity]),
             ('n', f'N {el}', O_LIGHT, [f'{v:,}' for v in g.n])]
    for ax, (col, lab, color, labels) in zip(axes, specs):
        colors = [O_PALE if m else color for m in muted]
        bars = ax.barh(y, g[col], color=colors)
        ax.set_yticks(y); ax.set_yticklabels(ticks); ax.set_xlim(0, g[col].max() * 1.35)
        ax.grid(axis='x', color='#e6e6e6'); ax.grid(axis='y', visible=False)
        _bar_labels(ax, bars, labels, muted=muted); _mute_ticks(ax, muted)
        ax.set_title(lab, loc='left', fontsize=9.5, fontweight='bold'); ax.xaxis.set_major_formatter(plt.FuncFormatter(_axis_num))
    fig.suptitle(f'{ml} by {dim} — total · per {el} · N', x=0.01, y=0.995, ha='left', va='top', fontsize=10.8, fontweight='bold')
    fig.text(0.01, 0.955, f'same {len(g)} rows across three panels, sorted by total; pale = n < {MIN_CELL_N}', fontsize=8, color='#666', va='top')
    plt.tight_layout(rect=(0, 0, 1, 0.92))
    table = g[::-1].round(2)
    note = (f'How to read: the same {len(g)} rows across three panels. A group can be big in total because it is many {el} '
            f'(right panel) or because each one is worth more (middle panel) — the trio separates the two. Pale bars: n < {MIN_CELL_N}.')
    return View(fig, table, note)


# ------------------------------------------------------------------ 3 penetration
def penetration(df, dim, flag, top_k=TOP_K, flag_label=None, entity=None):
    """Of each group in `dim`, what share has `flag` (0/1 or bool). HORIZONTAL bars, sorted by rate,
    overall rate as a GRAY reference line. Label: 'N split within group (penetration)'."""
    d = df.assign(_g=topk(df[dim], top_k), _f=df[flag].astype(float))
    if entity is not None:
        d = d.groupby(['_g', entity], observed=True)._f.max().reset_index()
    g = d.groupby('_g', observed=True)._f.agg(rate='mean', n='count', k='sum').sort_values('rate')
    overall = d._f.mean(); muted = (g.n < MIN_CELL_N).values
    fl = flag_label or flag
    fig, ax = plt.subplots(figsize=(8.5, 0.42 * len(g) + 2.0))
    y = np.arange(len(g))
    bars = ax.barh(y, g.rate, color=[O_PALE if m else O_MID for m in muted])
    ax.axvline(overall, color=GRAY, lw=1.2, ls='--'); ax.text(overall, len(g) - 0.4, f'overall {_pct(overall)}', fontsize=8, color='#666', ha='left', va='bottom')
    ax.set_yticks(y); ax.set_yticklabels([f'{i} (n={n:,})' for i, n in zip(g.index, g.n)])
    ax.set_xlim(0, max(g.rate.max(), overall) * 1.3); ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{100*v:.0f}%'))
    ax.grid(axis='x', color='#e6e6e6'); ax.grid(axis='y', visible=False)
    _bar_labels(ax, bars, [f'{_pct(r)} ({int(k):,}/{n:,})' for r, k, n in zip(g.rate, g.k, g.n)], muted=muted); _mute_ticks(ax, muted)
    titled(ax, f'{fl}: N split within group (penetration)', f'share of each {dim} group with {fl}; dashed = overall rate; pale = n < {MIN_CELL_N}')
    ax.set_xlabel(f'% of group with {fl}')
    plt.tight_layout()
    table = g[::-1].assign(rate=lambda t: t.rate.round(4))
    note = (f'How to read: each bar is a rate WITHIN its group and does not sum to 100% across bars. '
            f'"{table.index[0]}" has the highest rate ({_pct(table.rate.iloc[0])}); the dashed line is the pooled rate {_pct(overall)}. '
            f'A group can have a high rate and a small share of all flagged units — see the distribution view for the other axis.')
    return View(fig, table, note)


# ------------------------------------------------------------------ 4 mix
def mix(df, dim, by, top_k=TOP_K, by_k=5, entity=None):
    """Within each group of `dim`, how does `by` split. 100%-stacked HORIZONTAL bars; rows sorted by group
    size; segments = top-`by_k` values of `by` + Else, coloured BLACK (largest) then the orange ramp."""
    d = df.assign(_g=topk(df[dim], top_k), _b=topk(df[by], by_k))
    if entity is not None:
        d = d.drop_duplicates(['_g', '_b', entity])
    ct = pd.crosstab(d._g, d._b)
    ct = ct[ct.sum().sort_values(ascending=False).index]              # segments by overall size
    if ELSE in ct.columns:
        ct = ct[[c for c in ct.columns if c != ELSE] + [ELSE]]
    n = ct.sum(axis=1); ct = ct.loc[n.sort_values().index]; n = n.loc[ct.index]
    sh = ct.div(n, axis=0); muted = (n < MIN_CELL_N).values
    cols = [BLACK, O_DARK, O_MID, O_LIGHT, O_PALE, GRAY][:sh.shape[1]]
    fig, ax = plt.subplots(figsize=(9.5, 0.45 * len(sh) + 2.2))
    left = np.zeros(len(sh)); y = np.arange(len(sh))
    for c, colr in zip(sh.columns, cols):
        bars = ax.barh(y, sh[c], left=left, color=colr, label=str(c), alpha=None)
        for i, (b, v) in enumerate(zip(bars, sh[c])):
            if v >= 0.06:
                ax.text(b.get_x() + b.get_width() / 2, b.get_y() + b.get_height() / 2, _pct(v), ha='center', va='center',
                        fontsize=8, color='white' if colr in (BLACK, O_DARK, O_MID) else '#1a1a1a')
        left += sh[c].values
    ax.set_yticks(y); ax.set_yticklabels([f'{i} (n={k:,})' for i, k in zip(sh.index, n)]); _mute_ticks(ax, muted)
    ax.set_xlim(0, 1); ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{100*v:.0f}%'))
    ax.grid(axis='x', color='#e6e6e6'); ax.grid(axis='y', visible=False)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.12), ncol=min(6, sh.shape[1]), fontsize=8, title=by, title_fontsize=8)
    titled(ax, f'{by} mix within each {dim} group', f'each row sums to 100%; rows sorted by group size; segments = top {by_k} {by} values + Else; grey ticks = n < {MIN_CELL_N}')
    plt.tight_layout()
    table = sh[::-1].round(3).assign(n=n[::-1])
    note = (f'How to read: pick a row, read across — e.g. in "{table.index[0]}", {_pct(table.iloc[0, 0])} of units are "{table.columns[0]}". '
            f'Compare rows to see whether the {by} composition shifts across {dim}; a flat picture means {dim} and {by} are independent.')
    return View(fig, table, note)


# ------------------------------------------------------------------ 5 distribution
def distribution(df, dim, metric=None, top_k=TOP_K, entity=None, metric_label=None, entity_label=None):
    """Of the total, how it splits across `dim`. VERTICAL bars: share of entities (pale) and, if `metric`
    given, share of metric (dark) side by side. Label: 'share of each population (distribution)'."""
    d = df.assign(_g=topk(df[dim], top_k))
    if entity is not None:
        d = d.drop_duplicates(['_g', entity]) if metric is None else d
    cnt = d.groupby('_g', observed=True).size() if entity is None else d.groupby('_g', observed=True)[entity].nunique()
    tab = pd.DataFrame({'n': cnt, 'share_n': cnt / cnt.sum()})
    if metric is not None:
        m = d.groupby('_g', observed=True)[metric].sum(); tab['metric_total'] = m; tab['share_metric'] = m / m.sum()
    if not (isinstance(df[dim].dtype, pd.CategoricalDtype) and df[dim].dtype.ordered):
        tab = tab.sort_values('n', ascending=False)
    muted = (tab.n < MIN_CELL_N).values
    el, ml = entity_label or (entity or 'rows'), metric_label or metric
    fig, ax = plt.subplots(figsize=(max(7, 1.1 * len(tab) + 2), 4.2))
    x = np.arange(len(tab)); w = 0.38 if metric is not None else 0.6
    b1 = ax.bar(x - (w / 2 if metric is not None else 0), tab.share_n, width=w, color=[O_PALE if mm else O_LIGHT for mm in muted], label=f'share of {el}')
    _bar_labels(ax, b1, [_pct(v) for v in tab.share_n], horizontal=False, muted=muted)
    if metric is not None:
        b2 = ax.bar(x + w / 2, tab.share_metric, width=w, color=[O_PALE if mm else BLACK for mm in muted], label=f'share of {ml}')
        _bar_labels(ax, b2, [_pct(v) for v in tab.share_metric], horizontal=False, muted=muted)
        ax.legend(fontsize=8, loc='upper right')
    ax.set_xticks(x); ax.set_xticklabels([f'{i}\n(n={n:,})' for i, n in zip(tab.index, tab.n)], fontsize=8.5); _mute_ticks(ax, muted, axis='x')
    ax.set_ylim(0, max(tab.filter(like='share').max().max() * 1.25, 0.05)); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{100*v:.0f}%'))
    titled(ax, f'{dim}: share of each population (distribution)', f'each series sums to 100% across the bars; pale = n < {MIN_CELL_N}')
    plt.tight_layout()
    note = (f'How to read: bars sum to 100% across {dim}. ' +
            (f'Where the dark bar (share of {ml}) exceeds the light bar (share of {el}), that group punches above its weight per {el}. ' if metric is not None else '') +
            'This is the "of the total" view; the penetration view is the "of the group" view.')
    return View(fig, tab.round(4), note)


# ------------------------------------------------------------------ 6 time
def time_series(df, time_col, metric=None, freq='M', agg='sum', split=None, top_k=5, metric_label=None, entity=None):
    """metric by period (or count of rows / distinct entities if metric is None), optionally split by one
    dim (top-k + Else lines). True date axis; BLACK = total or the largest series."""
    d = df.copy(); d['_t'] = pd.to_datetime(d[time_col]).dt.to_period(freq).dt.to_timestamp()
    def _agg(gb):
        if metric is None:
            return gb[entity].nunique() if entity else gb.size()
        return getattr(gb[metric], agg)()
    if split is None:
        s = _agg(d.groupby('_t')); tab = s.to_frame('value')
        lines = {'total': s}
    else:
        d['_s'] = topk(d[split], top_k)
        tab = _agg(d.groupby(['_t', '_s'], observed=True)).unstack('_s').fillna(0)
        tab = tab[tab.sum().sort_values(ascending=False).index]
        lines = {c: tab[c] for c in tab.columns}
    ml = metric_label or (metric if metric else ('distinct ' + entity if entity else 'rows'))
    fig, ax = plt.subplots(figsize=(10, 4.2))
    cols = [BLACK, O_DARK, O_MID, O_LIGHT, O_PALE, GRAY]
    for (name, s), c in zip(lines.items(), cols):
        ax.plot(s.index, s.values, color=c, lw=2 if c == BLACK else 1.6, marker='o', ms=3, label=str(name))
        ax.annotate(_num(s.values[-1]), (s.index[-1], s.values[-1]), xytext=(4, 0), textcoords='offset points', fontsize=8, color=c if c != O_PALE else '#666', va='center')
    if len(lines) > 1:
        ax.legend(fontsize=8, title=split, title_fontsize=8)
    ax.set_ylim(bottom=0); ax.set_ylabel(f'{agg} {ml}' if metric else ml)
    first, last = tab.index.min(), tab.index.max()
    titled(ax, f'{ml} by {freq}-period' + (f', split by {split}' if split else ''), f'{first:%Y-%m-%d} to {last:%Y-%m-%d}; edge periods may be partial — check before reading a trend into them')
    plt.tight_layout()
    note = 'How to read: true date axis; the first and last periods are usually partial. Look for level shifts and seasonality before trends.'
    return View(fig, tab, note)


# ------------------------------------------------------------------ 7 saturation
def saturation(df, entity, count_col=None, marks=(0.8, 0.9, 0.95), label=None, max_k=None):
    """Cumulative % of entities with <= k of X, where X = rows per entity (count_col None) or the per-entity
    sum of count_col. Reports the k needed to reach each mark. STEP CDF."""
    per = df.groupby(entity).size() if count_col is None else df.groupby(entity)[count_col].sum()
    per = per.astype(int)
    vc = per.value_counts().sort_index(); cdf = vc.cumsum() / vc.sum()
    lab = label or (f'{count_col} per {entity}' if count_col else f'rows per {entity}')
    ks = {m: int(cdf.index[np.searchsorted(cdf.values, m)]) for m in marks}
    tab = pd.DataFrame({'k': cdf.index, 'entities': vc.values, 'cum_share': cdf.values.round(4)}).set_index('k')
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    xk = cdf.index.values if max_k is None else cdf.index.values[cdf.index.values <= max_k]
    xs = np.r_[xk[0] - 1, xk, xk[-1] + 1]; ys = np.r_[0.0, cdf.values[:len(xk)], cdf.values[len(xk) - 1]]
    ax.step(xs, ys, where='post', color=BLACK, lw=2)
    for m, c in zip(marks, [O_LIGHT, O_MID, O_DARK]):
        ax.axhline(m, color=c, lw=1, ls='--'); ax.axvline(ks[m], color=c, lw=1, ls=':')
        ax.annotate(f'{int(m*100)}% of {entity}s have ≤ {ks[m]}', (ks[m], m), xytext=(6, -12), textcoords='offset points', fontsize=8.5, color=c)
    ax.set_ylim(0, 1.02); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{100*v:.0f}%'))
    ax.set_xlabel(f'k = {lab}'); ax.set_ylabel(f'cumulative % of {entity}s with ≤ k')
    titled(ax, f'Saturation: {lab}', f'n = {len(per):,} {entity}s; median {int(per.median())}, max {int(per.max())}')
    plt.tight_layout()
    note = (f'How to read: to cover {int(marks[0]*100)}% of {entity}s you need k = {ks[marks[0]]}; the last {int((1-marks[-1])*100)}% need up to {int(per.max())}. '
            f'The flatter the tail, the more expensive each extra point of coverage.')
    return View(fig, tab, note), ks


# ------------------------------------------------------------------ 8 pareto
def pareto(df, entity, value, marks=(0.5, 0.8), label=None):
    """Lorenz / concentration: sort entities by value desc, cumulative share of value vs share of entities.
    Reports the smallest share of entities producing each mark of value (neutral tier names)."""
    per = df.groupby(entity)[value].sum().sort_values(ascending=False)
    per = per[per > 0]
    cum_v = per.cumsum() / per.sum(); cum_n = np.arange(1, len(per) + 1) / len(per)
    tiers = {m: (int(np.searchsorted(cum_v.values, m)) + 1) for m in marks}
    lab = label or f'{value} by {entity}'
    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.plot(np.r_[0, cum_n], np.r_[0, cum_v.values], color=BLACK, lw=2, label='cumulative share of value')
    ax.plot([0, 1], [0, 1], color=GRAY, lw=1, ls='--', label='perfect equality')
    for m, c in zip(marks, [O_MID, O_DARK]):
        k = tiers[m]; ax.scatter([k / len(per)], [m], color=c, s=40, zorder=4)
        ax.annotate(f'top {k:,} {entity}s ({_pct(k/len(per))}) = {int(m*100)}% of {value}', (k / len(per), m), xytext=(8, -14), textcoords='offset points', fontsize=8.5, color=c)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect('equal')
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{100*v:.0f}%')); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{100*v:.0f}%'))
    ax.set_xlabel(f'share of {entity}s (ranked by {value}, largest first)'); ax.set_ylabel(f'cumulative share of {value}')
    ax.legend(fontsize=8, loc='lower right')
    gini = 2 * np.trapz(np.r_[0, cum_v.values], np.r_[0, cum_n]) - 1 if len(per) > 1 else 0.0   # curve sits ABOVE the diagonal (descending sort)
    titled(ax, f'Concentration: {lab}', f'n = {len(per):,} {entity}s with {value} > 0; Gini {gini:.2f}')
    plt.tight_layout()
    tab = pd.DataFrame({'mark': [int(m*100) for m in marks], 'entities_needed': [tiers[m] for m in marks],
                        'share_of_entities': [round(tiers[m] / len(per), 4) for m in marks]}).set_index('mark')
    note = (f'How to read: the further the curve bows from the diagonal, the more concentrated the value. '
            f'{_pct(tiers[marks[-1]]/len(per))} of {entity}s produce {int(marks[-1]*100)}% of {value} — that set is the natural "core" tier (give it a neutral name).')
    return View(fig, tab, note), tiers
