"""nbx — extend a notebook in place: upsert one tagged section and execute only the setup cell(s) plus that section.

Live-interview mode for the /eda-* skills. Instead of regenerating the whole notebook from a builder (the default, and still
the right thing for a deliverable), this adds or replaces ONE (view, dimension) section in an existing .ipynb, runs just the
cells it needs (setup + the new one) in a fresh kernel, writes the notebook back, and returns the cell's printed table so the
caller can paste it. No PNG files: the chart lives in the notebook output.

    monaco-nb notebooks/eda_views.ipynb penetration --dim segment --flag repeat_90d --flag-label "repeat within 90d"
    monaco-nb notebooks/eda_views.ipynb trio --dim channel --metric revenue --metric-label "revenue ($)"
    monaco-nb new.ipynb structure --setup-file scripts/setup_df.py          # creates the notebook; setup must define `df`
    monaco-nb notebooks/eda_views.ipynb --columns                            # what is in df? (runs setup only, saves nothing)

Cells are addressed by tags in `cell.metadata.tags`: `nbx:setup` marks the setup cell(s) (fallback: the first code cell),
`nbx:section:<id>` marks a section's markdown + code pair, `nbx:stop` marks a trailing "stop condition" cell that new
sections are inserted before. `monaco.eda_build` writes these tags; notebooks built elsewhere work through the fallbacks.
"""
import argparse
import sys
from pathlib import Path

SETUP_TAG = 'nbx:setup'
STOP_TAG = 'nbx:stop'
SECTION_PREFIX = 'nbx:section:'
VIEWS = ('structure', 'trio', 'penetration', 'mix', 'distribution', 'time', 'saturation', 'pareto')
# arguments each view accepts (CLI flag -> keyword in the eda call), in call order
VIEW_ARGS = {
    'structure': [],
    'trio': ['dim', 'metric', 'entity', 'metric_label', 'entity_label'],
    'penetration': ['dim', 'flag', 'flag_label', 'entity'],
    'mix': ['dim', 'by', 'entity'],
    'distribution': ['dim', 'metric', 'entity', 'metric_label', 'entity_label'],
    'time': ['time_col', 'metric', 'freq', 'split', 'metric_label', 'entity'],
    'saturation': ['entity', 'count_col', 'label'],
    'pareto': ['entity', 'value', 'label'],
}
POSITIONAL = {'trio': ['dim', 'metric'], 'penetration': ['dim', 'flag'], 'mix': ['dim', 'by'], 'distribution': ['dim'],
              'time': ['time_col'], 'saturation': ['entity'], 'pareto': ['entity', 'value'], 'structure': []}
FUNC = {'time': 'time_series'}
IMPORT_LINE = 'from monaco.eda import structure, trio, penetration, mix, distribution, time_series, saturation, pareto'


# ------------------------------------------------------------------ tags
def tags(cell):
    return list(cell.get('metadata', {}).get('tags', []))


def tag(cell, *new):
    cell.setdefault('metadata', {})
    cell['metadata']['tags'] = sorted(set(tags(cell)) | set(new))
    return cell


def section_tag(section_id):
    return SECTION_PREFIX + section_id


def section_id_of(cell):
    for t in tags(cell):
        if t.startswith(SECTION_PREFIX):
            return t[len(SECTION_PREFIX):]
    return None


# ------------------------------------------------------------------ notebook IO
def load(path, title=None, setup_code=None):
    """Read the notebook, or create one with a title cell and a tagged setup cell when it does not exist (setup required)."""
    import nbformat as nbf
    path = Path(path)
    if path.exists():
        return nbf.read(str(path), as_version=4)
    if not setup_code:
        raise SystemExit(f'{path} does not exist; pass --setup-file (python that defines `df`) to create it')
    nb = nbf.v4.new_notebook()
    nb.cells.append(nbf.v4.new_markdown_cell(f"# {title or path.stem}\n\nBuilt live with `monaco-nb`; each section is one (view, dimension), tagged so it can be replaced in place."))
    nb.cells.append(tag(nbf.v4.new_code_cell(_setup_source(setup_code)), SETUP_TAG))
    return nb


def _setup_source(user_code):
    return ("import warnings; warnings.filterwarnings('ignore')\nimport pandas as pd, numpy as np\nimport matplotlib.pyplot as plt\n"
            "from monaco.viz import apply_style\n" + IMPORT_LINE + "\napply_style(dpi=110); pd.set_option('display.width', 220)\n\n"
            + user_code.strip() + "\nprint('df:', df.shape)")


def save(nb, path):
    import nbformat as nbf
    nbf.write(nb, str(path))


def setup_indices(nb):
    idx = [i for i, c in enumerate(nb.cells) if SETUP_TAG in tags(c)]
    if idx:
        return idx
    first = next((i for i, c in enumerate(nb.cells) if c.cell_type == 'code'), None)
    return [first] if first is not None else []


def find_section(nb, section_id):
    return [i for i, c in enumerate(nb.cells) if section_id_of(c) == section_id]


def upsert_section(nb, section_id, md_source, code_source):
    """Replace the section's cells in place if it exists, else insert before the stop cell (or append). Returns the code
    cell's index. Existing outputs of the replaced cells are cleared."""
    import nbformat as nbf
    t = section_tag(section_id)
    md = tag(nbf.v4.new_markdown_cell(md_source), t)
    code = tag(nbf.v4.new_code_cell(code_source), t)
    found = find_section(nb, section_id)
    if found:
        first = found[0]
        for i in sorted(found, reverse=True):
            del nb.cells[i]
        nb.cells[first:first] = [md, code]
        return first + 1
    stop = next((i for i, c in enumerate(nb.cells) if STOP_TAG in tags(c)), None)
    if stop is None:
        stop = next((i for i, c in enumerate(nb.cells) if c.cell_type == 'markdown' and c.source.lstrip().lower().startswith('## stop condition')), None)
    at = len(nb.cells) if stop is None else stop
    nb.cells[at:at] = [md, code]
    return at + 1


# ------------------------------------------------------------------ execution
def execute(nb, indices, workdir=None, timeout=600, kernel_name='python3'):
    """Run the setup cell(s) and then `indices`, in that order, in one fresh kernel. Other cells keep their stored outputs.
    Returns {index: stdout text} for the requested cells."""
    from nbclient import NotebookClient
    order = [i for i in setup_indices(nb) if i not in indices] + list(indices)
    client = NotebookClient(nb, timeout=timeout, kernel_name=kernel_name, resources={'metadata': {'path': workdir or '.'}})
    out = {}
    with client.setup_kernel():
        for i in order:
            cell = nb.cells[i]
            if cell.cell_type != 'code':
                continue
            client.execute_cell(cell, i)
            if i in indices:
                out[i] = stdout_of(cell)
    return out


def stdout_of(cell):
    parts = []
    for o in cell.get('outputs', []):
        if o.get('output_type') == 'stream':
            parts.append(o.get('text', ''))
        elif o.get('output_type') == 'error':
            parts.append('ERROR ' + o.get('ename', '') + ': ' + o.get('evalue', ''))
    return ''.join(parts)


def columns_of(nb, workdir=None, df='df'):
    """Run setup only and return df.dtypes as text (nothing is saved)."""
    import nbformat as nbf
    probe = nbf.v4.new_code_cell(f"print({df}.shape); print({df}.dtypes.to_string())\n"
                                 f"for c in {df}.columns:\n    s = {df}[c]\n"
                                 f"    if s.dtype == object or str(s.dtype) == 'category':\n"
                                 f"        vc = s.value_counts(dropna=False); print(f'-- {{c}}: {{len(vc)}} levels; top: ' + ', '.join(f'{{k}}={{v}}' for k, v in vc.head(5).items()))")
    nb.cells.append(probe)
    try:
        out = execute(nb, [len(nb.cells) - 1], workdir)
    finally:
        nb.cells.pop()
    return out[len(nb.cells)]


# ------------------------------------------------------------------ view cells
def render_call(view, params, df='df'):
    fn = FUNC.get(view, view)
    if view == 'structure':
        keys = params.get('keys')
        return f"structure(TABLES if 'TABLES' in dir() else {{'df': {df}}}, keys={keys!r})"
    pos = [repr(params[k]) for k in POSITIONAL[view] if params.get(k) is not None]
    kw = [f'{k}={params[k]!r}' for k in VIEW_ARGS[view] if k not in POSITIONAL[view] and params.get(k) is not None]
    return f"{fn}({', '.join([df] + pos + kw)})"


def view_cells(view, params, df='df', heading=None):
    """(markdown, code) for one view call, in the house pattern: print the table, print the note, show the chart."""
    from monaco.eda_build import WHAT
    call = render_call(view, params, df)
    what = {k: v for k, v in params.items() if v is not None and k in VIEW_ARGS[view]}
    head = heading or f"## {view} · " + ', '.join(f'{k}={v}' for k, v in what.items())
    md = f"{head}\n{WHAT[view]}"
    if view == 'structure':
        code = f"v = {call}\nprint(v.note)"
    elif view == 'saturation':
        code = f"v, ks = {call}\nprint(v.table.to_string()); print(); print('k needed:', ks); print(v.note)\nplt.show()"
    elif view == 'pareto':
        code = f"v, tiers = {call}\nprint(v.table.to_string()); print(); print(v.note)\nplt.show()"
    else:
        code = f"v = {call}\nprint(v.table.to_string())\nprint()\nprint(v.note)\nplt.show()"
    return md, code


def default_section_id(view, params):
    key = next((params[k] for k in POSITIONAL[view] if params.get(k)), None)
    return f'{view}:{key}' if key else view


def add_view(path, view, params, df='df', section_id=None, setup_code=None, title=None, workdir=None, run=True, heading=None):
    """The whole move: load/create → upsert the section → execute setup + section → save. Returns (code index, stdout)."""
    path = Path(path)
    nb = load(path, title=title, setup_code=setup_code)
    md, code = view_cells(view, params, df, heading)
    sid = section_id or default_section_id(view, params)
    i = upsert_section(nb, sid, md, code)
    text = ''
    if run:
        text = execute(nb, [i], workdir or str(path.parent))[i]
    save(nb, path)
    return i, text


# ------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('notebook')
    ap.add_argument('view', nargs='?', choices=VIEWS)
    ap.add_argument('--columns', action='store_true', help='run setup only and print df.dtypes + categorical levels; save nothing')
    for k in ('dim', 'metric', 'metric_label', 'entity', 'entity_label', 'flag', 'flag_label', 'by', 'time_col', 'freq', 'split', 'count_col', 'value', 'label'):
        ap.add_argument('--' + k.replace('_', '-'), dest=k)
    ap.add_argument('--keys', help="structure only: JSON like {\"df\": [[\"id\"]]}")
    ap.add_argument('--df', default='df', help='expression for the frame (default df)')
    ap.add_argument('--id', help='section id (default <view>:<dim|entity>); same id = replace in place')
    ap.add_argument('--heading', help='override the markdown heading')
    ap.add_argument('--setup-file', help='python that defines df; used only when the notebook does not exist yet')
    ap.add_argument('--title')
    ap.add_argument('--workdir')
    ap.add_argument('--no-run', action='store_true')
    a = ap.parse_args(argv)
    if a.columns:
        nb = load(a.notebook, setup_code=Path(a.setup_file).read_text() if a.setup_file else None, title=a.title)
        print(columns_of(nb, a.workdir or str(Path(a.notebook).parent), a.df))
        return
    if not a.view:
        ap.error('a view is required unless --columns is given')
    params = {k: getattr(a, k) for k in VIEW_ARGS[a.view]}
    if a.view == 'structure':
        import json
        params['keys'] = json.loads(a.keys) if a.keys else {}
    missing = [k for k in POSITIONAL[a.view] if not params.get(k)]
    if missing:
        ap.error(f"{a.view} needs --{' --'.join(m.replace('_', '-') for m in missing)}")
    setup = Path(a.setup_file).read_text() if a.setup_file else None
    i, text = add_view(a.notebook, a.view, params, df=a.df, section_id=a.id, setup_code=setup, title=a.title, workdir=a.workdir, run=not a.no_run, heading=a.heading)
    sys.stdout.write(text)
    print(f"\n[nbx] section '{a.id or default_section_id(a.view, params)}' at cell {i} of {a.notebook} — {'executed and saved' if not a.no_run else 'saved, not executed'}")


if __name__ == '__main__':
    main()
