"""health — partner (correspondent) health on a partner x month table + a partner x account roll-up.

Contracts (rename with --cols; anything extra is ignored):
    partner_month:    partner_id, month, new_accounts, kyc7_n, kyc7_k, fund30_n, fund30_k, funded_new, gross_deposits,
                      withdrawals, net_deposits, trading_accounts, fills, filled_notional
    partner_accounts: account_id, partner_id, funded, net_deposits, fills, filled_notional   (optional; concentration)

Views: concentration (eda_views.pareto + eda_views.distribution + a share table with HHI), per-partner trends with
95% intervals (small multiples), early-warning flags (latest complete month vs trailing-3-month baseline), readout.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from monaco import eda as eda_views
from monaco import readout as ds
from monaco import viz as dsviz
from monaco.stats import money, pct, wilson

BLACK, O_DARK, O_MID, O_LIGHT, O_PALE, GRAY = dsviz.BLACK, dsviz.O_DARK, dsviz.O_MID, dsviz.O_LIGHT, dsviz.O_PALE, dsviz.GRAY

# metric key: (label, kind, numerator col, denominator col)  kind ∈ rate | ratio | count | sum
METRICS = {
    'new_accounts':     ('new accounts', 'count', 'new_accounts', None),
    'kyc7':             ('KYC approved ≤7d', 'rate', 'kyc7_k', 'kyc7_n'),
    'fund30':           ('funded ≤30d', 'rate', 'fund30_k', 'fund30_n'),
    'funded_new':       ('newly funded accounts', 'count', 'funded_new', None),
    'gross_deposits':   ('gross deposits', 'sum', 'gross_deposits', None),
    'net_deposits':     ('net deposits', 'sum', 'net_deposits', None),
    'trading_accounts': ('trading accounts', 'count', 'trading_accounts', None),
    'fills_per_trader': ('fills per trading account', 'ratio', 'fills', 'trading_accounts'),
    'filled_notional':  ('filled notional', 'sum', 'filled_notional', None),
}
TREND_METRICS = ['fund30', 'net_deposits', 'fills_per_trader']
FLAG_METRICS = ['new_accounts', 'kyc7', 'fund30', 'net_deposits', 'trading_accounts', 'fills_per_trader', 'filled_notional']
REQUIRED = ['partner_id', 'month', 'new_accounts', 'kyc7_n', 'kyc7_k', 'fund30_n', 'fund30_k', 'funded_new', 'gross_deposits',
            'withdrawals', 'net_deposits', 'trading_accounts', 'fills', 'filled_notional']


# ------------------------------------------------------------------ 0 shape
def prepare(pm, as_of=None):
    missing = [c for c in REQUIRED if c not in pm.columns]
    if missing:
        raise SystemExit(f'partner_month is missing {missing}; map with --cols-month or edit sql/partner_month.sql')
    d = pm.copy(); d['month'] = pd.to_datetime(d['month']).dt.to_period('M').dt.to_timestamp()
    d = d.sort_values(['partner_id', 'month']).reset_index(drop=True)
    for c in REQUIRED[2:]:
        d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0.0)
    last_month = d.month.max()
    if as_of is None and 'as_of' in d.columns and d['as_of'].notna().any():
        as_of = pd.to_datetime(d['as_of']).max()                                   # carried through the SQL
    as_of = pd.Timestamp(as_of) if as_of is not None else last_month + pd.offsets.MonthEnd(0) - pd.Timedelta(days=1)  # unknown → assume partial
    partial = as_of < (last_month + pd.offsets.MonthEnd(0)).normalize()
    d['partial'] = (d.month == last_month) & partial
    last_complete = last_month - pd.offsets.MonthBegin(1) if partial else last_month
    for key, (lab, kind, num, den) in METRICS.items():
        if kind == 'rate':
            d[key], d[key + '_lo'], d[key + '_hi'] = wilson(d[num], d[den])
        elif kind == 'ratio':
            with np.errstate(divide='ignore', invalid='ignore'):
                m = np.where(d[den] > 0, d[num] / d[den], np.nan)
                se = np.sqrt(np.where(d[den] > 0, m / d[den], np.nan))             # Poisson counts per account
            d[key], d[key + '_lo'], d[key + '_hi'] = m, m - 1.96 * se, m + 1.96 * se
    d['funded_cum'] = d.groupby('partner_id').funded_new.cumsum()
    return d, as_of, last_complete


# ------------------------------------------------------------------ 1 concentration
def concentration(pm, pa, last_complete, trailing=3, out_figs=None):
    """Partner shares of accounts (lifetime), net deposits and filled notional (last `trailing` complete months).
    Charts: eda_views.pareto for accounts and notional; eda_views.distribution (share of accounts vs share of
    notional) when the account roll-up is available."""
    win = pm[(pm.month <= last_complete) & (pm.month > last_complete - pd.DateOffset(months=trailing))]
    agg = win.groupby('partner_id').agg(net_deposits_3m=('net_deposits', 'sum'), filled_notional_3m=('filled_notional', 'sum'),
                                        fills_3m=('fills', 'sum'), new_accounts_3m=('new_accounts', 'sum'))
    life = pm.groupby('partner_id').agg(accounts=('new_accounts', 'sum'), funded_accounts=('funded_new', 'sum'))
    tab = life.join(agg, how='left').fillna(0)
    shares = pd.DataFrame(index=tab.index)
    for c in ['accounts', 'funded_accounts', 'net_deposits_3m', 'filled_notional_3m']:
        v = tab[c].clip(lower=0); shares[f'share_{c}'] = v / v.sum() if v.sum() > 0 else np.nan
    tab = tab.join(shares).sort_values('accounts', ascending=False)
    hhi = {c: float((shares[f'share_{c}'].fillna(0) ** 2).sum()) for c in ['accounts', 'funded_accounts', 'net_deposits_3m', 'filled_notional_3m']}
    figs = {}
    v1, t1 = eda_views.pareto(tab.reset_index(), 'partner_id', 'accounts', label='accounts by partner (lifetime)')
    figs['pareto_accounts'] = (v1.fig, v1.table, v1.note)
    v2, t2 = eda_views.pareto(tab.reset_index(), 'partner_id', 'filled_notional_3m', label=f'filled notional by partner (last {trailing} complete months)')
    figs['pareto_notional'] = (v2.fig, v2.table, v2.note)
    if pa is not None and len(pa):
        v3 = eda_views.distribution(pa, 'partner_id', metric='filled_notional', entity='account_id', metric_label='filled notional (lifetime)', entity_label='accounts', top_k=8)
        figs['distribution_accounts_vs_notional'] = (v3.fig, v3.table, v3.note)
    return tab, hhi, figs


# ------------------------------------------------------------------ 2 early warning
def _pool(g, key):
    """Pooled value of a metric over a block of months: k/n for rates and ratios, mean for counts and sums."""
    lab, kind, num, den = METRICS[key]
    if kind in ('rate', 'ratio'):
        n = g[den].sum(); return (g[num].sum() / n if n > 0 else np.nan), n
    return g[key].mean(), len(g)


def _interval(g, key):
    """95% interval for the pooled baseline of a count/sum: mean ± 2 sd with a noise floor (rates/ratios use a two-sample test instead)."""
    lab, kind, num, den = METRICS[key]
    if kind == 'rate':
        n = g[den].sum(); _, lo, hi = wilson(g[num].sum(), n); return float(lo), float(hi)
    if kind == 'ratio':
        n = g[den].sum(); b = g[num].sum() / n if n > 0 else np.nan; se = np.sqrt(b / n) if n > 0 else np.nan; return b - 1.96 * se, b + 1.96 * se
    b, sd = g[key].mean(), g[key].std(ddof=0)
    sd = max(sd, 0.10 * abs(b), np.sqrt(abs(b)) if kind == 'count' else 0.0, 1e-9)        # floor: 10% of level, Poisson noise for counts
    return b - 2 * sd, b + 2 * sd


def early_warning(pm, last_complete, min_n=ds.MIN_GROUP_N, baseline_months=3, rel_threshold=0.20, pp_threshold=0.05, conc_threshold=0.25):
    """One row per (partner, metric, test) that trips a rule. Two tests, each against a pooled baseline:
      acute      latest complete month            vs the 3 months before it
      sustained  last 2 complete months pooled    vs the 3 months before those   (catches a shift that began last month)
    Gates (all must hold): value outside the baseline's 95% interval; the move NET OF THE PORTFOLIO'S OWN MOVE over the same
    months is ≥ pp_threshold (rates, percentage points) or ≥ rel_threshold (ratios, counts, sums, relative); the partner has
    ≥ min_n accounts of basis (else reported as thin). Plus: contraction (net deposits < 0 in both of the last two complete
    months) and concentration (≥ conc_threshold of portfolio accounts or of the month's notional), which are standing flags.
    Net-of-portfolio is the mix guard: a seasonal month moves every partner, and that is not a partner story."""
    rows = []
    tests = {'acute': (1, baseline_months), 'sustained': (2, baseline_months)}
    port = pm[pm.month <= last_complete].groupby('month')[[c for c in pm.columns if c in REQUIRED[2:]]].sum().sort_index()
    for key, (lab, kind, num, den) in METRICS.items():
        if kind in ('rate', 'ratio'):
            port[key] = np.where(port[den] > 0, port[num] / port[den], np.nan)
    tot_acc = pm.groupby('partner_id').new_accounts.sum()
    port_latest = pm[pm.month == last_complete].set_index('partner_id').filled_notional
    for pid, g in pm[pm.month <= last_complete].groupby('partner_id'):
        g = g.set_index('month').sort_index()
        if last_complete not in g.index:
            continue
        for test, (k_recent, k_base) in tests.items():
            recent_idx = g.index[g.index <= last_complete][-k_recent:]
            base_idx = g.index[g.index < recent_idx[0]][-k_base:]
            if len(recent_idx) < k_recent or len(base_idx) < 2:
                continue
            recent, base = g.loc[recent_idx], g.loc[base_idx]
            basis = int(max(base.new_accounts.sum() + recent.new_accounts.sum(), recent.trading_accounts.max()))
            thin = basis < min_n
            for key in FLAG_METRICS:
                lab, kind, num, den = METRICS[key]
                v, n_v = _pool(recent, key); b, n_b = _pool(base, key)
                if not (np.isfinite(v) and np.isfinite(b)) or b == 0:
                    continue
                if kind in ('rate', 'ratio'):                                     # two-sample test: both blocks carry sampling error
                    se = np.sqrt((v * (1 - v) / n_v if kind == 'rate' else v / n_v) + (b * (1 - b) / n_b if kind == 'rate' else b / n_b)) if n_v > 0 and n_b > 0 else np.nan
                    if not (np.isfinite(se) and abs(v - b) > 1.96 * se):
                        continue
                else:
                    lo, hi = _interval(base, key)
                    if not (v < lo or v > hi):
                        continue
                pv, _ = _pool(port.loc[recent_idx], key); pb, _ = _pool(port.loc[base_idx], key)
                if kind == 'rate':
                    move, port_move = v - b, (pv - pb if np.isfinite(pv) and np.isfinite(pb) else 0.0)
                    net = move - port_move; trip = abs(net) >= pp_threshold
                    move_s, net_s = f'{100*move:+.1f} pp', f'{100*net:+.1f} pp'
                else:
                    move, port_move = (v - b) / abs(b), ((pv - pb) / abs(pb) if np.isfinite(pv) and np.isfinite(pb) and pb else 0.0)
                    net = move - port_move; trip = abs(net) >= rel_threshold
                    move_s, net_s = f'{100*move:+.0f}%', f'{100*net:+.0f}%'
                if trip:
                    rows.append(dict(partner_id=pid, metric=lab, test=test, flag='drop' if v < b else 'spike', latest=v, baseline=b,
                                     move=move_s, net_of_portfolio=net_s, basis_accounts=basis, status='thin (not flagged)' if thin else 'FLAG', _sev=abs(net)))
        nd = g.net_deposits[g.index <= last_complete].tail(2)
        basis_c = int(g.new_accounts.tail(4).sum())
        if len(nd) == 2 and (nd < 0).all():
            rows.append(dict(partner_id=pid, metric='net deposits', test='sustained', flag='contraction (2 months < 0)', latest=nd.iloc[-1], baseline=nd.iloc[0],
                             move='', net_of_portfolio='', basis_accounts=basis_c, status='thin (not flagged)' if basis_c < min_n else 'FLAG', _sev=9.0))
    for pid in tot_acc.index:
        sa = tot_acc[pid] / tot_acc.sum(); sn = (port_latest.get(pid, 0) / port_latest.sum()) if port_latest.sum() > 0 else 0
        if max(sa, sn) >= conc_threshold:
            rows.append(dict(partner_id=pid, metric='portfolio share', test='standing', flag='concentration', latest=max(sa, sn), baseline=conc_threshold,
                             move='', net_of_portfolio='', basis_accounts=int(tot_acc[pid]), status='FLAG (standing)', _sev=max(sa, sn)))
    cols = ['partner_id', 'metric', 'test', 'flag', 'latest', 'baseline', 'move', 'net_of_portfolio', 'basis_accounts', 'status']
    out = pd.DataFrame(rows, columns=cols + ['_sev'])
    if len(out):
        out['_drop'] = out.flag.str.startswith(('drop', 'contraction')).astype(int)
        out = out.sort_values(['status', '_drop', '_sev'], ascending=[True, False, False])
        out = out.drop_duplicates(['partner_id', 'metric', 'flag'], keep='first')          # acute and sustained on the same move: keep the stronger
        out = out.drop(columns=['_sev', '_drop']).reset_index(drop=True)
    return out[cols]


# ------------------------------------------------------------------ 3 trends
def trends(pm, partners, last_complete, metrics=TREND_METRICS, months=12, flags=None):
    """Small multiples: rows = partners, cols = metrics; 95% interval band for rates/ratios, trailing-3-month
    baseline band (mean ± 2 sd, GRAY) for sums/counts; the partial month is hollow; a flagged latest point is O_DARK."""
    flags = flags if flags is not None else pd.DataFrame(columns=['partner_id', 'metric', 'status'])
    lo_m = last_complete - pd.DateOffset(months=months - 1)
    fig, axes = plt.subplots(len(partners), len(metrics), figsize=(4.0 * len(metrics) + 0.5, 1.75 * len(partners) + 1.2), squeeze=False, sharex=True)
    for ri, pid in enumerate(partners):
        g = pm[(pm.partner_id == pid) & (pm.month >= lo_m)].set_index('month').sort_index()
        for ci, key in enumerate(metrics):
            ax = axes[ri, ci]; lab, kind, num, den = METRICS[key]
            comp = g[~g.partial]; part = g[g.partial]
            flagged = ((flags.partner_id == pid) & (flags.metric == lab) & flags.status.str.startswith('FLAG')).any()
            if kind in ('rate', 'ratio'):
                ax.fill_between(g.index, g[key + '_lo'], g[key + '_hi'], color=O_LIGHT, alpha=0.35, lw=0)
            else:
                base = comp[comp.index < last_complete].tail(3)[key]
                if len(base) >= 2:
                    m, sd = base.mean(), max(base.std(ddof=0), 0.10 * abs(base.mean()))
                    ax.axhspan(m - 2 * sd, m + 2 * sd, color='#eeeeee', lw=0)
                    ax.axhline(m, color=GRAY, lw=0.8, ls='--')
            ax.plot(comp.index, comp[key], color=BLACK, lw=1.6, marker='o', ms=3)
            if len(part):
                ax.plot(list(comp.index[-1:]) + list(part.index), list(comp[key].iloc[-1:]) + list(part[key]), color=BLACK, lw=1, ls=':')
                ax.plot(part.index, part[key], marker='o', ms=4, mfc='white', mec=BLACK, ls='none')
            if last_complete in comp.index:
                v = comp.loc[last_complete, key]
                ax.plot([last_complete], [v], marker='o', ms=6 if flagged else 4, color=O_DARK if flagged else BLACK)
                txt = pct(v) if kind == 'rate' else (money(v) if kind == 'sum' else f'{v:,.1f}' if kind == 'ratio' else f'{v:,.0f}')
                ax.annotate(txt, (last_complete, v), xytext=(5, 0), textcoords='offset points', fontsize=8, color=O_DARK if flagged else BLACK, va='center')
            if kind == 'rate':
                ax.set_ylim(0, 1); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{100*v:.0f}%'))
            elif kind == 'sum':
                ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: money(v)))
                ax.axhline(0, color='#bbbbbb', lw=0.8)
            else:
                ax.set_ylim(bottom=0)
            if ri == 0:
                ax.set_title(lab, loc='left', fontsize=9.5, fontweight='bold')
            if ci == 0:
                ax.set_ylabel(pid, fontsize=9, fontweight='bold', rotation=0, ha='right', va='center', labelpad=28)
            ax.tick_params(axis='x', labelsize=7.5, rotation=0); ax.tick_params(axis='y', labelsize=7.5)
    fig.suptitle(f'Per-partner trends, last {months} months to {last_complete:%Y-%m} (last complete month)', x=0.01, y=0.995, ha='left', va='top', fontsize=10.8, fontweight='bold')
    fig.text(0.01, 0.975, 'orange band = 95% interval (Wilson for rates, Poisson for fills per account); grey band = trailing-3-month baseline ± 2 sd; hollow = partial month; dark-orange point = flagged',
             fontsize=8, color='#666', va='top')
    plt.tight_layout(rect=(0, 0, 1, 0.95))
    note = ('How to read: one row per partner, one column per metric; read a row left to right to see whether a funding drop is also a trading drop. '
            'Points inside the band are noise at this partner size; the flag table lists only the points outside it with a ≥ 20% move.')
    return fig, note
