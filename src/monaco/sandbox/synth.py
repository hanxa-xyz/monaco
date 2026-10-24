"""synth — synthetic Broker API rows with the REAL field names and enum values.

Used by load_sandbox.py when live sandbox credentials are absent. Everything is deterministic for a seed.
The generator bakes in four partner scenarios so the two skills have something to find:

    MEGA  one partner is ~35% of accounts (concentration / mix trap)
    KYCD  KYC approval rate drops ~25 pts for accounts created from 2026-08 (early-warning test)
    CNTR  deposits fall, withdrawals triple from 2026-08 (contraction flag)
    RAMP  onboarded 2026-05 and growing fast (new-partner ramp; thin, early cohorts)

Grain reminders baked into the shapes: accounts are not humans; `orders.status` is a current state; fills
live in `activities`; a RETURNED transfer is a deposit that un-happened; journals move firm <-> user only.
"""
from __future__ import annotations

import uuid

import numpy as np
import pandas as pd

PARTNER_TYPES = ['fintech', 'neobank', 'ria', 'bd', 'crypto_exchange']
TYPE_P = [0.35, 0.20, 0.20, 0.15, 0.10]
COUNTRIES = ['US', 'US', 'US', 'GB', 'BR', 'JP', 'NG', 'SG', 'CA']

# symbol: (base price, asset_class, exchange, pays dividends)
SYMBOLS = {
    'AAPL': (230.0, 'us_equity', 'NASDAQ', True), 'MSFT': (420.0, 'us_equity', 'NASDAQ', True),
    'NVDA': (125.0, 'us_equity', 'NASDAQ', False), 'TSLA': (250.0, 'us_equity', 'NASDAQ', False),
    'AMZN': (185.0, 'us_equity', 'NASDAQ', False), 'SPY': (560.0, 'us_equity', 'ARCA', True),
    'VOO': (515.0, 'us_equity', 'ARCA', True), 'QQQ': (480.0, 'us_equity', 'NASDAQ', True),
    'META': (520.0, 'us_equity', 'NASDAQ', False), 'AMD': (160.0, 'us_equity', 'NASDAQ', False),
    'PLTR': (30.0, 'us_equity', 'NASDAQ', False), 'SOFI': (8.0, 'us_equity', 'NASDAQ', False),
    'F': (12.0, 'us_equity', 'NYSE', True), 'KO': (62.0, 'us_equity', 'NYSE', True),
    'BTC/USD': (65000.0, 'crypto', 'CRYPTO', False), 'ETH/USD': (3200.0, 'crypto', 'CRYPTO', False),
    'SOL/USD': (150.0, 'crypto', 'CRYPTO', False),
}
EQ = [s for s, v in SYMBOLS.items() if v[1] == 'us_equity']
EQ_W = np.array([10, 7, 9, 9, 6, 8, 5, 5, 4, 4, 5, 4, 2, 2], dtype=float); EQ_W /= EQ_W.sum()
CR = [s for s, v in SYMBOLS.items() if v[1] == 'crypto']
CR_W = np.array([0.6, 0.3, 0.1])

# per partner type: kyc pass, fund rate, trade rate | funded, fills per month, deposit median $, crypto share, notional-order share
TYPE_PARAMS = {
    'fintech':         dict(kyc=0.88, fund=0.55, trade=0.75, lam=4.0, dep=300.0, crypto=0.10, notional=0.65),
    'neobank':         dict(kyc=0.84, fund=0.45, trade=0.60, lam=2.5, dep=200.0, crypto=0.05, notional=0.75),
    'ria':             dict(kyc=0.95, fund=0.70, trade=0.55, lam=1.2, dep=8000.0, crypto=0.00, notional=0.20),
    'bd':              dict(kyc=0.99, fund=0.60, trade=0.80, lam=6.0, dep=3000.0, crypto=0.02, notional=0.10),
    'crypto_exchange': dict(kyc=0.82, fund=0.50, trade=0.85, lam=8.0, dep=500.0, crypto=0.85, notional=0.80),
}


def _uuids(rng, n):
    hi = rng.integers(0, 2**62, size=n, dtype=np.int64); lo = rng.integers(0, 2**62, size=n, dtype=np.int64)
    return np.array([str(uuid.UUID(int=(int(a) << 64) | int(b), version=4)) for a, b in zip(hi, lo)], dtype=object)


def _ts(base, days):
    """base: datetime64[ns] array/scalar; days: float array -> Timestamp array (ns)."""
    return pd.to_datetime(base) + pd.to_timedelta(np.asarray(days, dtype=float) * 86400.0, unit='s')


def _lognorm_days(rng, median_days, sigma, n):
    return rng.lognormal(np.log(median_days), sigma, n)


# ------------------------------------------------------------------ partners
def gen_partners(rng, n_partners, start, as_of):
    codes = set(); out = []
    while len(out) < n_partners:
        c = ''.join(rng.choice(list('ABCDEFGHJKLMNPQRSTUVWXYZ'), 4))
        if c not in codes:
            codes.add(c); out.append(c)
    codes = np.array(out, dtype=object)
    codes[:4] = ['MEGA', 'KYCD', 'CNTR', 'RAMP']
    types = rng.choice(PARTNER_TYPES, n_partners, p=TYPE_P).astype(object)
    types[0] = 'fintech'; types[1] = 'neobank'; types[2] = 'fintech'; types[3] = 'fintech'
    weight = rng.lognormal(0.0, 1.0, n_partners); weight[0] = weight.sum() * 0.55; weight[1] = np.median(weight) * 5.0; weight[2] = np.median(weight) * 3.0; weight[3] = np.median(weight) * 1.5
    months_before = rng.integers(0, 20, n_partners)
    onboarded = (pd.Timestamp(start) - pd.to_timedelta(months_before * 30, unit='D')).normalize()
    onboarded = pd.DatetimeIndex(onboarded).to_series().reset_index(drop=True)
    onboarded.iloc[3] = pd.Timestamp('2026-05-04')
    late = rng.random(n_partners) < 0.2                                  # some partners joined mid-window
    late[:4] = False
    onboarded[late] = pd.Timestamp(start) + pd.to_timedelta(rng.integers(30, 400, late.sum()), unit='D')
    df = pd.DataFrame({
        'correspondent': codes, 'partner_name': ['Partner ' + c for c in codes], 'partner_type': types,
        'country': rng.choice(COUNTRIES, n_partners), 'onboarded_at': onboarded.dt.date,
        'kyc_flow': np.where(types == 'bd', 'fully_disclosed_bd', 'alpaca_kyc'),
        'instant_funding': np.isin(types, ['fintech', 'neobank']) & (rng.random(n_partners) < 0.4),
        '_weight': weight,
    })
    for k in ['kyc', 'fund', 'trade', 'lam', 'dep', 'crypto', 'notional']:
        base = df.partner_type.map(lambda t: TYPE_PARAMS[t][k]).astype(float)
        jitter = rng.normal(1.0, 0.08, n_partners)
        df['_' + k] = (base * jitter).clip(lower=0.0)
    df['_kyc'] = df['_kyc'].clip(upper=0.995)
    df['_fund'] = df['_fund'].clip(upper=0.9); df['_trade'] = df['_trade'].clip(upper=0.95)
    df['_firm_account'] = _uuids(rng, n_partners)                            # firm/sweep account per partner (journals)
    return df


# ------------------------------------------------------------------ accounts + status events
def gen_accounts(rng, partners, start, as_of, n_target):
    months = pd.period_range(pd.Timestamp(start), pd.Timestamp(as_of), freq='M')
    w = partners._weight.values / partners._weight.sum()
    rows = []
    for mi, m in enumerate(months):
        growth = 1.0 + 0.035 * mi                                           # portfolio grows ~3.5%/month
        seas = 1.15 if m.month in (1, 2, 3) else (0.9 if m.month in (7, 8) else 1.0)
        for pi in range(len(partners)):
            onb = pd.Timestamp(partners.onboarded_at.iloc[pi])
            if m.end_time < onb:
                continue
            age_m = max(0, (m.start_time.year - onb.year) * 12 + m.start_time.month - onb.month)
            ramp = min(1.0, (age_m + 1) / 6.0)                               # six-month ramp after onboarding
            if partners.correspondent.iloc[pi] == 'RAMP':
                ramp = 1.0 + 0.6 * age_m                                     # the fast-growing new partner
            lam = n_target / len(months) * w[pi] * growth * seas * ramp
            k = rng.poisson(lam)
            if k == 0:
                continue
            lo, hi = m.start_time, min(m.end_time, pd.Timestamp(as_of))
            secs = rng.random(k) * (hi - lo).total_seconds()
            rows.append(pd.DataFrame({'_p': pi, 'created_at': lo + pd.to_timedelta(secs, unit='s')}))
    acc = pd.concat(rows, ignore_index=True).sort_values('created_at').reset_index(drop=True)
    n = len(acc)
    acc['id'] = _uuids(rng, n)
    acc['account_number'] = [f'{rng.integers(100, 999)}{c}{rng.integers(100000, 999999)}' for c in partners.correspondent.values[acc._p.values]]
    acc['correspondent'] = partners.correspondent.values[acc._p.values]
    ptype = partners.partner_type.values[acc._p.values]
    acc['account_type'] = np.where(ptype == 'ria', rng.choice(['trading', 'ira', 'joint'], n, p=[0.7, 0.2, 0.1]),
                                   rng.choice(['trading', 'custodial'], n, p=[0.97, 0.03]))
    acc['currency'] = 'USD'
    flow = partners.kyc_flow.values[acc._p.values]
    p_pass = partners._kyc.values[acc._p.values].copy()
    kycd = (acc.correspondent.values == 'KYCD') & (acc.created_at.values >= np.datetime64('2026-08-01'))
    p_pass[kycd] -= 0.25
    u = rng.random(n)
    fd = flow == 'fully_disclosed_bd'
    passed = u < p_pass
    # branch for non-pass under Alpaca KYC: ACTION_REQUIRED (60%) or APPROVAL_PENDING (40%)
    branch = np.where(rng.random(n) < 0.6, 'AR', 'AP')
    ar_out = rng.choice(['approve', 'stuck', 'reject'], n, p=[0.55, 0.30, 0.15])
    ap_out = rng.choice(['approve', 'reject'], n, p=[0.75, 0.25])
    created = acc.created_at.values
    ev = []  # (account idx, at, status_to, reason)

    def add(mask, at, status, reason=None):
        idx = np.nonzero(mask)[0]
        if len(idx):
            ev.append(pd.DataFrame({'_i': idx, 'at': np.asarray(at)[idx] if np.ndim(at) else at, 'status_to': status, 'reason': reason}))

    # entry status
    add(~fd, created, 'SUBMITTED')
    add(fd, created, 'APPROVED')
    approved_at = np.full(n, np.datetime64('NaT'), dtype='datetime64[ns]')
    rejected_at = np.full(n, np.datetime64('NaT'), dtype='datetime64[ns]')
    # fully disclosed: 99% go ACTIVE within minutes, 1% REJECTED (blacklist)
    fd_rej = fd & (rng.random(n) < 0.01)
    approved_at[fd & ~fd_rej] = created[fd & ~fd_rej]
    rejected_at[fd_rej] = _ts(created[fd_rej], rng.uniform(0.01, 0.2, fd_rej.sum())).values
    # alpaca kyc: pass -> APPROVED after ~30 min median
    m = ~fd & passed
    approved_at[m] = _ts(created[m], _lognorm_days(rng, 0.02, 1.0, m.sum())).values
    # non-pass, ACTION_REQUIRED branch
    m_ar = ~fd & ~passed & (branch == 'AR')
    ar_at = _ts(created, rng.uniform(0.02, 0.1, n)).values
    add(m_ar, ar_at, 'ACTION_REQUIRED', 'ADDRESS_VERIFICATION')
    m_ar_ok = m_ar & (ar_out == 'approve'); m_ar_rej = m_ar & (ar_out == 'reject')
    approved_at[m_ar_ok] = _ts(ar_at[m_ar_ok], rng.uniform(1, 10, m_ar_ok.sum())).values
    rejected_at[m_ar_rej] = _ts(ar_at[m_ar_rej], rng.uniform(2, 15, m_ar_rej.sum())).values
    # non-pass, APPROVAL_PENDING branch
    m_ap = ~fd & ~passed & (branch == 'AP')
    ap_at = _ts(created, rng.uniform(0.02, 0.1, n)).values
    add(m_ap, ap_at, 'APPROVAL_PENDING', 'WATCHLIST_HIT')
    m_ap_ok = m_ap & (ap_out == 'approve'); m_ap_rej = m_ap & (ap_out == 'reject')
    approved_at[m_ap_ok] = _ts(ap_at[m_ap_ok], rng.uniform(0.5, 5, m_ap_ok.sum())).values
    rejected_at[m_ap_rej] = _ts(ap_at[m_ap_rej], rng.uniform(1, 7, m_ap_rej.sum())).values
    has_appr = ~np.isnat(approved_at)
    add(has_appr & ~fd, approved_at, 'APPROVED')
    active_at = np.full(n, np.datetime64('NaT'), dtype='datetime64[ns]')
    active_at[has_appr] = _ts(approved_at[has_appr], rng.uniform(0.001, 0.02, has_appr.sum())).values
    add(has_appr, active_at, 'ACTIVE')
    add(~np.isnat(rejected_at), rejected_at, 'REJECTED', 'IDENTITY_VERIFICATION')
    # 2% of active accounts close later
    closed_at = np.full(n, np.datetime64('NaT'), dtype='datetime64[ns]')
    cl = has_appr & (rng.random(n) < 0.02)
    closed_at[cl] = _ts(active_at[cl], rng.exponential(200, cl.sum()) + 30).values
    add(cl, closed_at, 'ACCOUNT_CLOSED')

    events = pd.concat(ev, ignore_index=True)
    events['at'] = pd.to_datetime(events['at'])
    events = events[events["at"] <= pd.Timestamp(as_of)].sort_values(['_i', 'at'], kind='mergesort').reset_index(drop=True)
    events['status_from'] = events.groupby('_i').status_to.shift(1)
    events['account_id'] = acc.id.values[events._i.values]
    events['account_number'] = acc.account_number.values[events._i.values]
    events['event_id'] = np.arange(1, len(events) + 1)
    acc['status'] = events.groupby('_i').status_to.last().reindex(range(n)).values
    acc['crypto_status'] = np.where(partners._crypto.values[acc._p.values] > 0.03, acc.status, 'INACTIVE')
    acc['enabled_assets'] = [['us_equity', 'crypto'] if c else ['us_equity'] for c in acc.crypto_status != 'INACTIVE']
    acc['kyc_summary'] = np.where(has_appr, 'pass', np.where(~np.isnat(rejected_at), 'fail', None))
    acc['_active_at'] = pd.to_datetime(active_at); acc.loc[acc._active_at > pd.Timestamp(as_of), '_active_at'] = pd.NaT
    acc['_closed_at'] = pd.to_datetime(closed_at); acc.loc[acc._closed_at > pd.Timestamp(as_of), '_closed_at'] = pd.NaT
    return acc, events[['event_id', 'account_id', 'account_number', 'at', 'status_from', 'status_to', 'reason']]


# ------------------------------------------------------------------ funding: transfers + journals
def gen_funding(rng, partners, acc, as_of):
    as_of = pd.Timestamp(as_of)
    P = partners.iloc[acc._p.values].reset_index(drop=True)
    elig = acc._active_at.notna().values
    fund_p = P._fund.values.copy()
    cntr_late = (acc.correspondent.values == 'CNTR') & (acc.created_at.values >= np.datetime64('2026-08-01'))
    fund_p[cntr_late] -= 0.15
    funded = elig & (rng.random(len(acc)) < fund_p)
    idx = np.nonzero(funded)[0]
    first_at = _ts(acc._active_at.values[idx], _lognorm_days(rng, 1.2, 1.3, len(idx)))
    keep = first_at <= as_of
    idx, first_at = idx[keep], first_at[keep]
    dep_med = P._dep.values[idx]
    amt = np.round(rng.lognormal(np.log(dep_med), 0.9, len(idx)), 2)
    rows = [pd.DataFrame({'_i': idx, 'created_at': first_at, 'amount': amt, 'direction': 'INCOMING', '_kind': 'first'})]
    # recurring deposits: 40% of funded accounts, ~0.6/month over their life
    months_alive = np.clip(((as_of - first_at) / pd.Timedelta(days=30)).values.astype(float), 0.1, None)
    rec = rng.random(len(idx)) < 0.4
    k_rec = rng.poisson(0.6 * months_alive * rec)
    ri = np.repeat(idx, k_rec); r0 = np.repeat(first_at.values, k_rec)
    r_at = pd.to_datetime(r0) + pd.to_timedelta(rng.random(len(ri)) * (as_of - pd.to_datetime(r0)).total_seconds(), unit='s')
    rows.append(pd.DataFrame({'_i': ri, 'created_at': r_at, 'amount': np.round(rng.lognormal(np.log(np.repeat(dep_med, k_rec)), 0.8), 2),
                              'direction': 'INCOMING', '_kind': 'recurring'}))
    # withdrawals: 30% of funded accounts, ~0.25/month
    wd = rng.random(len(idx)) < 0.3
    k_wd = rng.poisson(0.25 * months_alive * wd)
    wi = np.repeat(idx, k_wd); w0 = np.repeat(first_at.values, k_wd)
    w_at = pd.to_datetime(w0) + pd.to_timedelta(rng.random(len(wi)) * (as_of - pd.to_datetime(w0)).total_seconds(), unit='s') + pd.Timedelta(days=7)
    rows.append(pd.DataFrame({'_i': wi, 'created_at': w_at, 'amount': np.round(rng.lognormal(np.log(np.repeat(dep_med, k_wd) * 0.7), 0.8), 2),
                              'direction': 'OUTGOING', '_kind': 'withdrawal'}))
    t = pd.concat(rows, ignore_index=True)
    t = t[t.created_at <= as_of].reset_index(drop=True)
    # contraction scenario: from 2026-08 the CNTR partner's deposits thin out and withdrawals triple
    is_cntr = (acc.correspondent.values[t._i.values] == 'CNTR') & (t.created_at.values >= np.datetime64('2026-08-01'))
    drop_dep = is_cntr & (t.direction.values == 'INCOMING') & (t._kind.values != 'first') & (rng.random(len(t)) < 0.6)
    t = t[~drop_dep].reset_index(drop=True)
    is_cntr = (acc.correspondent.values[t._i.values] == 'CNTR') & (t.created_at.values >= np.datetime64('2026-08-01'))
    extra = t[is_cntr & (t.direction.values == 'OUTGOING')]
    t = pd.concat([t, extra, extra], ignore_index=True)
    n = len(t)
    # status mix; failed first attempts retry once, half the time
    st = rng.choice(['COMPLETE', 'RETURNED', 'REJECTED', 'CANCELED'], n, p=[0.90, 0.04, 0.04, 0.02]).astype(object)
    recent = (as_of - t.created_at) < pd.Timedelta(days=3)
    st[recent.values & (st == 'COMPLETE')] = rng.choice(['QUEUED', 'PENDING', 'SENT_TO_CLEARING', 'COMPLETE'], recent.sum() if False else (recent.values & (st == 'COMPLETE')).sum(), p=[0.2, 0.4, 0.2, 0.2])
    t['status'] = st
    fail = (t.status.isin(['REJECTED', 'CANCELED', 'RETURNED']) & (t._kind == 'first')).values
    retry = fail & (rng.random(n) < 0.5)
    rt = t[retry].copy(); rt['created_at'] = rt.created_at + pd.to_timedelta(rng.uniform(1, 5, len(rt)), unit='D')
    rt['status'] = rng.choice(['COMPLETE', 'REJECTED'], len(rt), p=[0.85, 0.15]); rt['_kind'] = 'retry'
    rt = rt[rt.created_at <= as_of]
    t = pd.concat([t, rt], ignore_index=True); n = len(t)
    t['id'] = _uuids(rng, n)
    t['account_id'] = acc.id.values[t._i.values]
    t['relationship_id'] = acc.id.values[t._i.values]  # one bank link per account in the synthetic world
    t['type'] = np.where(t.amount > 25000, 'wire', 'ach')
    done = t.status.isin(['COMPLETE', 'RETURNED', 'REJECTED', 'CANCELED']).values
    t['updated_at'] = t.created_at + pd.to_timedelta(np.where(done, rng.uniform(1, 4, n), rng.uniform(0, 0.5, n)), unit='D')
    t.loc[t.status == 'RETURNED', 'updated_at'] += pd.Timedelta(days=4)
    t['updated_at'] = t.updated_at.clip(upper=as_of)
    t['expires_at'] = t.created_at + pd.Timedelta(days=7)
    t['hold_until'] = (t.updated_at + pd.Timedelta(days=2)).where(t.status == 'COMPLETE')
    t['instant_amount'] = np.where((t.type == 'ach') & (t.direction == 'INCOMING') & (rng.random(n) < 0.3), np.minimum(t.amount, 1000.0), 0.0)
    t['reason'] = np.where(t.status == 'RETURNED', 'R01 insufficient funds', np.where(t.status == 'REJECTED', 'name mismatch', None))
    transfers = t[['id', 'account_id', 'relationship_id', 'type', 'status', 'amount', 'direction', 'created_at', 'updated_at',
                   'expires_at', 'hold_until', 'instant_amount', 'reason', '_i']]
    # journals: instant-funding partners push a JNLC from the firm account at activation; JNLS share rewards
    inst = P.instant_funding.values[idx] & (rng.random(len(idx)) < 0.7)
    ji = idx[inst]
    j_at = _ts(acc._active_at.values[ji], rng.uniform(0.001, 0.05, len(ji)))
    j_amt = np.minimum(amt[inst], 1000.0).round(2)
    j_status = rng.choice(['executed', 'executed', 'executed', 'pending', 'rejected', 'queued'], len(ji), p=[0.3, 0.3, 0.3, 0.04, 0.04, 0.02])
    jn = pd.DataFrame({'_i': ji, 'from_account': P._firm_account.values[ji], 'to_account': acc.id.values[ji], 'entry_type': 'JNLC',
                       'status': j_status, 'net_amount': j_amt, 'symbol': None, 'qty': np.nan, 'price': np.nan,
                       'description': 'instant funding advance', 'created_at': j_at})
    promo = P.instant_funding.values[idx] & (rng.random(len(idx)) < 0.08)
    si = idx[promo]
    sym = rng.choice(['AAPL', 'F', 'SOFI', 'KO'], len(si))
    px = np.array([SYMBOLS[s][0] for s in sym])
    js = pd.DataFrame({'_i': si, 'from_account': P._firm_account.values[si], 'to_account': acc.id.values[si], 'entry_type': 'JNLS',
                       'status': 'executed', 'net_amount': np.nan, 'symbol': sym, 'qty': 1.0, 'price': px,
                       'description': 'sign-up share reward', 'created_at': _ts(first_at.values[promo], rng.uniform(0.5, 2, len(si)))})
    j = pd.concat([jn, js], ignore_index=True)
    j = j[j.created_at <= as_of].reset_index(drop=True)
    j['id'] = _uuids(rng, len(j)); j['currency'] = 'USD'
    j['system_date'] = j.created_at.dt.date; j['settle_date'] = (j.created_at + pd.Timedelta(days=1)).dt.date
    journals = j[['id', 'from_account', 'to_account', 'entry_type', 'status', 'net_amount', 'symbol', 'qty', 'price', 'description',
                  'currency', 'settle_date', 'system_date', 'created_at', '_i']]
    return transfers, journals


def funded_at(acc, transfers, journals):
    a = transfers[(transfers.status == 'COMPLETE') & (transfers.direction == 'INCOMING')].groupby('_i').updated_at.min()
    b = journals[(journals.status == 'executed') & (journals.entry_type == 'JNLC')].groupby('_i').created_at.min()
    f = pd.concat([a, b]).groupby(level=0).min()
    return f.reindex(range(len(acc)))


# ------------------------------------------------------------------ trading: orders + fills
def gen_orders(rng, partners, acc, f_at, start, as_of):
    as_of = pd.Timestamp(as_of); P = partners.iloc[acc._p.values].reset_index(drop=True)
    fidx = np.nonzero(f_at.notna().values)[0]
    trader = rng.random(len(fidx)) < P._trade.values[fidx]
    ti = fidx[trader]
    first = _ts(f_at.values[ti], _lognorm_days(rng, 0.8, 1.4, len(ti)))
    keep = first <= as_of; ti, first = ti[keep], first[keep]
    lam = rng.gamma(1.3, P._lam.values[ti] / 1.3)                                  # fills / month per account
    horizon = first + pd.to_timedelta(rng.exponential(270, len(ti)), unit='D')     # churn
    end = pd.DatetimeIndex(np.minimum(horizon.values, as_of.to_datetime64()))
    months = ((end - first) / pd.Timedelta(days=30)).values.clip(min=0)
    k = np.minimum(rng.poisson(lam * months), 400)
    n_first = len(ti); n_rest = int(k.sum())
    oi = np.r_[ti, np.repeat(ti, k)]
    o_first = np.r_[first.values, pd.to_datetime(np.repeat(first.values, k)).values]
    span = np.r_[np.zeros(n_first), np.repeat((end - first).total_seconds().values, k)]
    at = pd.to_datetime(o_first) + pd.to_timedelta(rng.random(len(oi)) * span, unit='s')
    is_first = np.r_[np.ones(n_first, bool), np.zeros(n_rest, bool)]
    n = len(oi)
    crypto = rng.random(n) < P._crypto.values[oi]
    sym = np.where(crypto, rng.choice(CR, n, p=CR_W), rng.choice(EQ, n, p=EQ_W)).astype(object)
    base = np.array([SYMBOLS[s][0] for s in sym])
    t_days = (at - pd.Timestamp(start)).total_seconds().values / 86400.0
    price = base * np.exp(0.0004 * t_days + rng.normal(0, 0.03, n))
    side = np.where(is_first, 'buy', np.where(rng.random(n) < 0.62, 'buy', 'sell')).astype(object)
    otype = rng.choice(['market', 'limit', 'stop', 'stop_limit', 'trailing_stop'], n, p=[0.70, 0.24, 0.03, 0.02, 0.01]).astype(object)
    tif = np.where(otype == 'market', 'day', rng.choice(['day', 'gtc'], n, p=[0.5, 0.5])).astype(object)
    use_notional = (rng.random(n) < P._notional.values[oi]) & (side == 'buy')
    notional = np.where(use_notional, np.round(rng.lognormal(np.log(P._dep.values[oi] * 0.25), 0.9, n), 2), np.nan)
    qty = np.where(use_notional, np.nan, np.where(crypto, np.round(rng.lognormal(-3, 1, n), 6), np.maximum(1, np.round(rng.lognormal(1.2, 1.0, n)))))
    status = rng.choice(['filled', 'canceled', 'expired', 'rejected', 'partially_filled', 'replaced', 'new'], n,
                        p=[0.86, 0.07, 0.02, 0.015, 0.01, 0.005, 0.02]).astype(object)
    status[is_first & np.isin(status, ['rejected', 'replaced', 'new'])] = 'filled'
    old = (as_of - at) > pd.Timedelta(days=1)
    status[(status == 'new') & np.asarray(old)] = 'filled'
    status[(status == 'canceled') & (otype == 'market')] = 'filled'                 # market orders rarely cancel
    filled = np.isin(status, ['filled', 'partially_filled'])
    fill_delay = np.where(otype == 'market', rng.uniform(0.2, 5, n), rng.uniform(60, 6 * 3600, n))  # seconds
    filled_at = pd.Series(at + pd.to_timedelta(fill_delay, unit='s')).where(filled)
    filled_at = filled_at.clip(upper=as_of)
    req_qty = np.where(use_notional, notional / price, qty)
    frac = np.where(status == 'partially_filled', rng.uniform(0.2, 0.8, n), 1.0)
    filled_qty = np.where(filled, req_qty * frac, 0.0)
    filled_qty = np.where(crypto | use_notional, np.round(filled_qty, 6), np.floor(filled_qty))
    filled_qty = np.where(filled & (filled_qty <= 0), req_qty, filled_qty)
    filled_avg_price = np.where(filled, np.round(price * np.exp(rng.normal(0, 0.001, n)), 2), np.nan)
    limit_price = np.where(np.isin(otype, ['limit', 'stop_limit']), np.round(price * np.where(side == 'buy', 0.99, 1.01), 2), np.nan)
    stop_price = np.where(np.isin(otype, ['stop', 'stop_limit']), np.round(price * np.where(side == 'buy', 1.02, 0.97), 2), np.nan)
    o = pd.DataFrame({
        '_i': oi, 'id': _uuids(rng, n), 'client_order_id': [f'{c}-{i:08d}' for i, c in enumerate(acc.correspondent.values[oi])],
        'account_id': acc.id.values[oi], 'created_at': at, 'submitted_at': at + pd.to_timedelta(rng.uniform(0.01, 0.3, n), unit='s'),
        'filled_at': filled_at.values,
        'expired_at': pd.Series(at + pd.Timedelta(hours=8)).where(status == 'expired').values,
        'canceled_at': pd.Series(at + pd.to_timedelta(rng.uniform(60, 7200, n), unit='s')).where(status == 'canceled').values,
        'failed_at': pd.Series(at + pd.Timedelta(seconds=1)).where(status == 'rejected').values,
        'asset_id': [str(uuid.uuid5(uuid.NAMESPACE_DNS, s)) for s in sym], 'symbol': sym,
        'asset_class': np.where(crypto, 'crypto', 'us_equity'), 'notional': notional, 'qty': qty, 'filled_qty': filled_qty,
        'filled_avg_price': filled_avg_price, 'order_class': 'simple', 'type': otype, 'side': side, 'time_in_force': tif,
        'limit_price': limit_price, 'stop_price': stop_price, 'status': status, 'extended_hours': rng.random(n) < 0.03,
        'commission': 0.0, '_is_first': is_first,
    })
    o['updated_at'] = o[['filled_at', 'expired_at', 'canceled_at', 'failed_at', 'submitted_at']].bfill(axis=1).iloc[:, 0]
    o = o[o.created_at <= as_of].sort_values('created_at').reset_index(drop=True)
    return o


def gen_fill_activities(rng, orders):
    f = orders[orders.status.isin(['filled', 'partially_filled'])].reset_index(drop=True)
    n = len(f)
    split = (f.status == 'filled').values & (rng.random(n) < 0.08)                 # two-part fills
    part_share = rng.uniform(0.3, 0.7, n)
    rows = []
    # partial rows: for split orders (first leg) and for partially_filled orders (only leg)
    p_mask = split | (f.status == 'partially_filled').values
    pq = np.where(split, f.filled_qty.values * part_share, f.filled_qty.values)
    rows.append(pd.DataFrame({
        'account_id': f.account_id.values[p_mask], 'order_id': f.id.values[p_mask],
        'transaction_time': (f.filled_at - pd.to_timedelta(np.where(split, rng.uniform(5, 600, n), 0), unit='s')).values[p_mask],
        'type': 'partial_fill', 'price': f.filled_avg_price.values[p_mask], 'qty': pq[p_mask], 'side': f.side.values[p_mask],
        'symbol': f.symbol.values[p_mask], 'cum_qty': pq[p_mask],
        'leaves_qty': np.where(split, f.filled_qty.values - pq, (f.qty.fillna(f.notional / f.filled_avg_price).values - f.filled_qty.values).clip(min=0))[p_mask],
        'order_status': 'partially_filled'}))
    full = (f.status == 'filled').values
    rows.append(pd.DataFrame({
        'account_id': f.account_id.values[full], 'order_id': f.id.values[full], 'transaction_time': f.filled_at.values[full], 'type': 'fill',
        'price': f.filled_avg_price.values[full], 'qty': np.where(split, f.filled_qty.values - pq, f.filled_qty.values)[full],
        'side': f.side.values[full], 'symbol': f.symbol.values[full], 'cum_qty': f.filled_qty.values[full], 'leaves_qty': 0.0,
        'order_status': 'filled'}))
    a = pd.concat(rows, ignore_index=True)
    a['activity_type'] = 'FILL'
    a['id'] = [f"{pd.Timestamp(t).strftime('%Y%m%d%H%M%S%f')}::{u}" for t, u in zip(a.transaction_time, _uuids(rng, len(a)))]
    return a


def gen_nontrade_activities(rng, acc, transfers, journals, orders, f_at, as_of):
    as_of = pd.Timestamp(as_of); rows = []
    tc = transfers[transfers.status == 'COMPLETE']
    rows.append(pd.DataFrame({'account_id': tc.account_id.values, 'activity_type': np.where(tc.direction == 'INCOMING', 'CSD', 'CSW'),
                              'date': tc.updated_at.dt.date.values, 'net_amount': np.where(tc.direction == 'INCOMING', tc.amount, -tc.amount),
                              'description': np.where(tc.type == 'ach', 'ACH ' + tc.direction.str.lower(), 'WIRE ' + tc.direction.str.lower()),
                              'transfer_id': tc.id.values, 'status': 'executed'}))
    je = journals[journals.status == 'executed']
    rows.append(pd.DataFrame({'account_id': je.to_account.values, 'activity_type': je.entry_type.values, 'date': je.created_at.dt.date.values,
                              'net_amount': je.net_amount.values, 'symbol': je.symbol.values, 'qty': je.qty.values,
                              'description': je.description.values, 'status': 'executed'}))
    # FEE on equity sells (REG + TAF), one row each
    s = orders[(orders.status == 'filled') & (orders.side == 'sell') & (orders.asset_class == 'us_equity')]
    notional = s.filled_qty * s.filled_avg_price
    rows.append(pd.DataFrame({'account_id': s.account_id.values, 'activity_type': 'FEE', 'date': s.filled_at.dt.date.values,
                              'net_amount': -np.round(notional.values * 0.0000278, 2), 'symbol': s.symbol.values, 'description': 'REG fee',
                              'activity_sub_type': 'REG', 'status': 'executed'}))
    rows.append(pd.DataFrame({'account_id': s.account_id.values, 'activity_type': 'FEE', 'date': s.filled_at.dt.date.values,
                              'net_amount': -np.round(np.minimum(s.filled_qty.values * 0.000166, 8.3), 2), 'symbol': s.symbol.values,
                              'description': 'TAF fee', 'activity_sub_type': 'TAF', 'status': 'executed'}))
    # DIV at quarter ends for net-long holders of dividend payers
    div_syms = [k for k, v in SYMBOLS.items() if v[3]]
    d = orders[(orders.status == 'filled') & orders.symbol.isin(div_syms)]
    signed = d.filled_qty * np.where(d.side == 'buy', 1, -1)
    for qe in pd.date_range(pd.Timestamp('2025-06-30'), as_of, freq='QE'):
        held = signed[d.filled_at <= qe].groupby([d.account_id, d.symbol]).sum()
        held = held[held > 0].reset_index(); held.columns = ['account_id', 'symbol', 'qty']
        if held.empty:
            continue
        psa = held.symbol.map({s: round(SYMBOLS[s][0] * 0.0035, 4) for s in div_syms})
        rows.append(pd.DataFrame({'account_id': held.account_id.values, 'activity_type': 'DIV', 'date': (qe + pd.Timedelta(days=12)).date(),
                                  'net_amount': np.round(held.qty.values * psa.values, 2), 'symbol': held.symbol.values, 'qty': held.qty.values,
                                  'per_share_amount': psa.values, 'description': 'Cash DIV', 'activity_sub_type': 'CDIV', 'status': 'executed'}))
    # INT monthly on an estimate of idle cash (cash sweep, 3% APY)
    dep = transfers[(transfers.status == 'COMPLETE')].assign(signed=lambda t: np.where(t.direction == 'INCOMING', t.amount, -t.amount))
    inv = orders[orders.status == 'filled'].assign(signed=lambda o: -o.filled_qty * o.filled_avg_price * np.where(o.side == 'buy', 1, -1))
    flows = pd.concat([dep[['account_id', 'updated_at', 'signed']].rename(columns={'updated_at': 'ts'}),
                       inv[['account_id', 'filled_at', 'signed']].rename(columns={'filled_at': 'ts'})])
    for me in pd.date_range(pd.Timestamp('2025-04-30'), as_of, freq='ME'):
        cash = flows[flows.ts <= me].groupby('account_id').signed.sum()
        cash = cash[cash > 50]
        if cash.empty:
            continue
        rows.append(pd.DataFrame({'account_id': cash.index.values, 'activity_type': 'INT', 'date': me.date(),
                                  'net_amount': np.round(cash.values * 0.03 / 12, 2), 'description': 'Cash sweep interest',
                                  'activity_sub_type': 'MGN' if False else 'INT', 'status': 'executed'}))
    a = pd.concat(rows, ignore_index=True)
    a = a[(a.net_amount.abs() >= 0.01) | (a.activity_type == 'JNLS')].reset_index(drop=True)
    a['id'] = [f"{pd.Timestamp(d).strftime('%Y%m%d')}000000000::{u}" for d, u in zip(a.date, _uuids(rng, len(a)))]
    return a


def gen_positions(rng, acc, orders, start, as_of):
    f = orders[orders.status.isin(['filled', 'partially_filled'])]
    signed = f.filled_qty * np.where(f.side == 'buy', 1, -1)
    g = pd.DataFrame({'account_id': f.account_id, 'symbol': f.symbol, 'signed': signed,
                      'buy_cost': np.where(f.side == 'buy', f.filled_qty * f.filled_avg_price, 0), 'buy_qty': np.where(f.side == 'buy', f.filled_qty, 0)})
    p = g.groupby(['account_id', 'symbol']).sum().reset_index()
    p = p[p.signed > 1e-9].reset_index(drop=True)
    T = (pd.Timestamp(as_of) - pd.Timestamp(start)).days
    base = p.symbol.map(lambda s: SYMBOLS[s][0]).values
    cur = base * np.exp(0.0004 * T) * np.exp(rng.normal(0, 0.01, len(p)))
    last = cur / np.exp(rng.normal(0, 0.012, len(p)))
    out = pd.DataFrame({
        'account_id': p.account_id, 'asset_id': [str(uuid.uuid5(uuid.NAMESPACE_DNS, s)) for s in p.symbol], 'symbol': p.symbol,
        'exchange': p.symbol.map(lambda s: SYMBOLS[s][2]), 'asset_class': p.symbol.map(lambda s: SYMBOLS[s][1]),
        'avg_entry_price': np.round(p.buy_cost / p.buy_qty, 4), 'qty': p.signed, 'qty_available': p.signed, 'side': 'long',
        'market_value': np.round(p.signed * cur, 2), 'cost_basis': np.round(p.signed * (p.buy_cost / p.buy_qty), 2),
        'current_price': np.round(cur, 4), 'lastday_price': np.round(last, 4), 'change_today': np.round(cur / last - 1, 6),
        'asset_marginable': p.symbol.map(lambda s: SYMBOLS[s][1] == 'us_equity'),
    })
    out['unrealized_pl'] = np.round(out.market_value - out.cost_basis, 2)
    out['unrealized_plpc'] = np.round(out.unrealized_pl / out.cost_basis, 6)
    return out


# ------------------------------------------------------------------ orchestrator
def generate(seed=7, n_partners=36, n_accounts=40000, start='2025-04-01', as_of='2026-10-22'):
    rng = np.random.default_rng(seed)
    partners = gen_partners(rng, n_partners, start, as_of)
    acc, events = gen_accounts(rng, partners, start, as_of, n_accounts)
    transfers, journals = gen_funding(rng, partners, acc, as_of)
    f_at = funded_at(acc, transfers, journals)
    orders = gen_orders(rng, partners, acc, f_at, start, as_of)
    fills = gen_fill_activities(rng, orders)
    nta = gen_nontrade_activities(rng, acc, transfers, journals, orders, f_at, as_of)
    activities = pd.concat([fills, nta], ignore_index=True)
    positions = gen_positions(rng, acc, orders, start, as_of)
    # last_equity = positions + idle cash estimate
    mv = positions.groupby('account_id').market_value.sum()
    dep = transfers[transfers.status == 'COMPLETE'].assign(s=lambda t: np.where(t.direction == 'INCOMING', t.amount, -t.amount)).groupby('account_id').s.sum()
    inv = orders[orders.status == 'filled'].assign(s=lambda o: o.filled_qty * o.filled_avg_price * np.where(o.side == 'buy', 1, -1)).groupby('account_id').s.sum()
    eq = (dep.reindex(acc.id).fillna(0).values - inv.reindex(acc.id).fillna(0).values + mv.reindex(acc.id).fillna(0).values).clip(min=0)
    acc['last_equity'] = np.round(eq, 2)
    cols = {
        'partners': partners[['correspondent', 'partner_name', 'partner_type', 'country', 'onboarded_at', 'kyc_flow', 'instant_funding']],
        'accounts': acc[['id', 'account_number', 'correspondent', 'status', 'crypto_status', 'currency', 'last_equity', 'created_at',
                         'account_type', 'enabled_assets', 'kyc_summary']],
        'account_status_events': events,
        'orders': orders[['id', 'client_order_id', 'account_id', 'created_at', 'updated_at', 'submitted_at', 'filled_at', 'expired_at',
                          'canceled_at', 'failed_at', 'asset_id', 'symbol', 'asset_class', 'notional', 'qty', 'filled_qty', 'filled_avg_price',
                          'order_class', 'type', 'side', 'time_in_force', 'limit_price', 'stop_price', 'status', 'extended_hours', 'commission']],
        'positions': positions,
        'activities': activities,
        'transfers': transfers.drop(columns=['_i']),
        'journals': journals.drop(columns=['_i']),
    }
    return cols
