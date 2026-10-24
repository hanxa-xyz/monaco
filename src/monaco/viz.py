"""viz — the house visual toolkit (palette, chart grammar, notebook helpers).

Import this; never re-declare palette constants in a notebook or script.

Palette semantics
-----------------
BLACK  = hero series / totals / the top tier.
Orange ramp O_PALE -> O_LIGHT -> O_MID -> O_DARK = ordered magnitude (pale = baseline / "neither").
GRAY   = reference lines. One hue + black; never blue.

Chart grammar (see docs/PLAYBOOK.md for the full rules)
-------------------------------------------------------
- Penetration views are HORIZONTAL bars; distribution views are VERTICAL bars.
  Fixed row labels: "N split within group (penetration)" / "share of each population (distribution)".
- Direct value label on every bar; n= counts in the tick labels.
- titled(ax, title, subtitle): bold left title + gray definitional subtitle.
- Footnotes go through save_fig(footnote_text=...) and render as HTML under the chart via img() —
  never fig.text into the PNG.
- Mute cells with n < MIN_CELL_N (grey text, excluded from any shared color scale).
"""
import base64
import io

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# ---------------------------------------------------------------- palette
BLACK, O_DARK, O_MID, O_LIGHT, O_PALE = '#1a1a1a', '#b34212', '#eb6834', '#f4a06f', '#fbd9c4'
GRAY = '#9a9a9a'
PAL = [BLACK, O_MID, O_DARK, O_LIGHT, O_PALE, O_MID, O_DARK, O_LIGHT]
RAMP4 = [O_PALE, O_LIGHT, O_MID, O_DARK]
WY = LinearSegmentedColormap.from_list('white_yellow', ['#ffffff', '#ffe066', '#f5c518'])

MIN_CELL_N = 15          # below this, a cell mean is too thin to trust: grey it, drop from color scale


def apply_style(dpi=150):
    """House rcParams. dpi=150 for report figures, 110 for notebooks."""
    plt.rcParams.update({'figure.dpi': dpi, 'axes.spines.top': False, 'axes.spines.right': False,
        'axes.grid': True, 'axes.grid.axis': 'y', 'grid.color': '#e6e6e6', 'grid.linewidth': .8,
        'axes.axisbelow': True, 'font.size': 10, 'legend.frameon': False,
        'savefig.bbox': 'tight', 'savefig.facecolor': 'white'})


def titled(ax, title, subtitle, pad=22):
    """Bold left-aligned title + gray definitional subtitle above the axes."""
    ax.set_title(title, loc='left', fontsize=10.8, fontweight='bold', pad=pad)
    ax.text(0, 1.04, subtitle, transform=ax.transAxes, fontsize=8.0, color='#666')


# ------------------------------------------------- figure store (report builders)
FIGS, NOTES = {}, {}


def save_fig(fig, name, footnote_text=None):
    """Render fig to a palette-quantized base64 PNG in FIGS. Footnote text is stored out-of-band
    in NOTES and rendered as HTML by img() — never drawn into the image."""
    from PIL import Image
    if footnote_text:
        NOTES[name] = footnote_text
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    im = Image.open(buf).convert('RGB')
    if im.width > 1250:
        im = im.resize((1250, int(im.height * 1250 / im.width)), Image.LANCZOS)
    im = im.convert('P', palette=Image.ADAPTIVE, colors=128)
    out = io.BytesIO()
    im.save(out, format='PNG', optimize=True)
    FIGS[name] = base64.b64encode(out.getvalue()).decode()


def img(name):
    """Embed a stored figure as a self-contained <img>, with its footnote as selectable HTML.
    Remember: any literal '<' in footnote text must be written as &lt; (it is raw HTML)."""
    tag = f'<img src="data:image/png;base64,{FIGS[name]}" style="max-width:100%">'
    note = NOTES.get(name)
    if note:
        note = note.replace('\\$', '$')      # undo the matplotlib mathtext escape for HTML
        tag += f'\n<p class="fignote"><b>Note:</b> {note}</p>'
    return tag


# ------------------------------------------------- notebook builders
def new_notebook():
    import nbformat as nbf
    return nbf.v4.new_notebook()


def md(source):
    import nbformat as nbf
    return nbf.v4.new_markdown_cell(source)


def code(source):
    import nbformat as nbf
    return nbf.v4.new_code_cell(source)


def build_and_execute(nb, path, workdir=None, timeout=900):
    """Write the notebook, execute it, write again with outputs baked in.

    The write-twice pattern is deliberate: the first write leaves a readable notebook even if a
    cell fails; the second persists outputs. Any failing cell raises, so the notebook can never
    ship stale or broken.

    Escaping asymmetry to remember when authoring cells as triple-quoted strings in a builder
    script: cell sources are plain (non-f) strings, so {} need no doubling, but \\n and \\$ must be
    escaped or the BUILDER's parser consumes them. (Report f-strings are the opposite: {} doubled.)
    """
    import os

    import nbformat as nbf
    from nbclient import NotebookClient
    nbf.write(nb, path)
    client = NotebookClient(nb, timeout=timeout, kernel_name='python3',
                            resources={'metadata': {'path': workdir or os.path.dirname(path) or '.'}})
    client.execute()
    nbf.write(nb, path)
    print('EXECUTED OK')
