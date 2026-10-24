"""readout — print every table you chart, save PNGs, and write a readout that cannot skip the close.

The close is five lines, always in this order:
    Headline -> Go / No-go -> Action -> Guardrail -> Revisit
A readout written through write_readout() with any line missing shows [TODO] in its place; the gap is
visible, never silently dropped. Lines the code drafts from numbers are tagged [draft]: prompts to finish,
not conclusions.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from monaco import viz

MIN_GROUP_N = 100          # below this a group's rate is reported but never flagged


def setup(dpi=130):
    viz.apply_style(dpi=dpi)
    pd.set_option('display.width', 220); pd.set_option('display.max_columns', 40); pd.set_option('display.max_rows', 200)


def save_png(fig, out_dir, name):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f'{name}.png'
    fig.savefig(p); plt.close(fig)
    return p


def print_table(title, df, note=None):
    print(f'\n== {title}')
    print(df.to_string() if isinstance(df, pd.DataFrame) else df)
    if note:
        print(note)


def md_table(df, max_rows=60):
    """Minimal GitHub-markdown table without the tabulate dependency."""
    d = df.reset_index() if df.index.name or not isinstance(df.index, pd.RangeIndex) else df
    d = d.head(max_rows)

    def fmt(v):
        if isinstance(v, float):
            return '' if np.isnan(v) else (f'{v:,.3f}' if abs(v) < 10 else f'{v:,.0f}')
        return str(v)
    head = '| ' + ' | '.join(map(str, d.columns)) + ' |'
    sep = '|' + '|'.join(['---'] * len(d.columns)) + '|'
    rows = ['| ' + ' | '.join(fmt(v) for v in r) + ' |' for r in d.itertuples(index=False)]
    tail = [f'_{len(df) - max_rows} more rows in the CSV_'] if len(df) > max_rows else []
    return '\n'.join([head, sep] + rows + tail)


CLOSE_KEYS = ['headline', 'decision', 'action', 'guardrail', 'revisit']
CLOSE_TEMPLATE = """
## Close (fill every line; a readout without all five is not done)
**Headline:** {headline}
**Go / No-go:** {decision}
**Action:** {action}
**Guardrail:** {guardrail}
**Revisit:** {revisit}
"""


def render_close(close):
    return CLOSE_TEMPLATE.format(**{k: close.get(k) or '[TODO]' for k in CLOSE_KEYS})


def write_readout(path, title, sections, close):
    """sections: list of (heading, markdown-or-DataFrame). close: dict with the five CLOSE_KEYS."""
    lines = [f'# {title}', '']
    for h, body in sections:
        lines += [f'## {h}', '']
        lines += [md_table(body) if isinstance(body, pd.DataFrame) else str(body), '']
    lines.append(render_close(close))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text('\n'.join(lines))
    return path
