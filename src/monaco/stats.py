"""stats — the small set of statistics the readouts need, vectorised, NaN where undefined."""
from __future__ import annotations

import numpy as np

Z95 = 1.959964


def wilson(k, n, z=Z95):
    """Wilson score interval for a binomial rate. Returns (rate, lo, hi) arrays with NaN where n == 0."""
    k = np.asarray(k, dtype=float); n = np.asarray(n, dtype=float)
    with np.errstate(divide='ignore', invalid='ignore'):
        p = np.where(n > 0, k / n, np.nan)
        den = 1 + z**2 / n
        centre = (p + z**2 / (2 * n)) / den
        half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return p, np.where(n > 0, centre - half, np.nan), np.where(n > 0, centre + half, np.nan)


def pct(v):
    """0.1234 -> '12%'; 0.0123 -> '1.2%'; None/NaN -> '—'."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '—'
    return f'{100*v:.0f}%' if v >= 0.10 else f'{100*v:.1f}%'


def money(v):
    """1_234_567 -> '$1.2M'; 12_345 -> '$12k'; 1_234 -> '$1,234'; negatives keep the sign."""
    a = abs(v)
    s = f'${a/1e6:.1f}M' if a >= 1e6 else (f'${a/1e3:.0f}k' if a >= 1e4 else f'${a:,.0f}')
    return ('-' if v < 0 else '') + s
