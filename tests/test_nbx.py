import json

import pytest

from monaco import nbx

SETUP = "df = pd.DataFrame({'seg': list('aabbbc'), 'flag': [1, 0, 1, 1, 0, 0], 'rev': [10, 20, 5, 5, 5, 1], 'id': range(6)})"


def _nb(tmp_path):
    return nbx.load(tmp_path / 'x.ipynb', title='t', setup_code=SETUP)


def test_render_call_positional_and_keywords():
    assert nbx.render_call('penetration', {'dim': 'seg', 'flag': 'flag', 'flag_label': 'f', 'entity': None}) == \
        "penetration(df, 'seg', 'flag', flag_label='f')"
    assert nbx.render_call('trio', {'dim': 'seg', 'metric': 'rev', 'entity': 'id', 'metric_label': None, 'entity_label': None}) == \
        "trio(df, 'seg', 'rev', entity='id')"
    assert nbx.render_call('time', {'time_col': 'd', 'metric': None, 'freq': 'W', 'split': None, 'metric_label': None, 'entity': None}) == \
        "time_series(df, 'd', freq='W')"
    assert nbx.render_call('structure', {'keys': {'df': [['id']]}}).startswith('structure(')


def test_new_notebook_has_tagged_setup(tmp_path):
    nb = _nb(tmp_path)
    assert nbx.setup_indices(nb) == [1]
    assert nbx.SETUP_TAG in nbx.tags(nb.cells[1])


def test_upsert_replaces_in_place_and_inserts_before_stop(tmp_path):
    import nbformat as nbf
    nb = _nb(tmp_path)
    nb.cells.append(nbx.tag(nbf.v4.new_markdown_cell('## Stop condition'), nbx.STOP_TAG))
    i = nbx.upsert_section(nb, 'penetration:seg', '## p', 'v = 1')
    assert i == 3 and len(nb.cells) == 5 and nbx.STOP_TAG in nbx.tags(nb.cells[-1])
    j = nbx.upsert_section(nb, 'penetration:seg', '## p2', 'v = 2')
    assert j == 3 and len(nb.cells) == 5 and nb.cells[3].source == 'v = 2'
    k = nbx.upsert_section(nb, 'trio:seg', '## t', 'v = 3')
    assert k == 5 and len(nb.cells) == 7 and nbx.section_id_of(nb.cells[4]) == 'trio:seg'


def test_untagged_notebook_falls_back_to_first_code_cell(tmp_path):
    import nbformat as nbf
    nb = nbf.v4.new_notebook(); nb.cells = [nbf.v4.new_markdown_cell('x'), nbf.v4.new_code_cell('a = 1'), nbf.v4.new_code_cell('b = 2')]
    assert nbx.setup_indices(nb) == [1]
    i = nbx.upsert_section(nb, 's', '## s', 'c = 3')
    assert i == 4 and len(nb.cells) == 5


@pytest.mark.skipif(pytest.importorskip('ipykernel', reason='no kernel') is None, reason='no kernel')
def test_add_view_executes_only_setup_and_section(tmp_path):
    path = tmp_path / 'live.ipynb'
    i, text = nbx.add_view(path, 'penetration', {'dim': 'seg', 'flag': 'flag', 'flag_label': 'flag', 'entity': None}, setup_code=SETUP, workdir=str(tmp_path))
    assert 'rate' in text and 'how to read' in text.lower()
    import nbformat as nbf
    nb = nbf.read(str(path), as_version=4)
    code = nb.cells[i]
    assert any(o.get('data', {}).get('image/png') for o in code.outputs), 'chart should be in the notebook output'
    # second view: the first section's outputs are kept, not re-executed
    first_outputs = json.dumps(code.outputs)
    j, text2 = nbx.add_view(path, 'trio', {'dim': 'seg', 'metric': 'rev', 'entity': None, 'metric_label': None, 'entity_label': None}, workdir=str(tmp_path))
    nb2 = nbf.read(str(path), as_version=4)
    assert json.dumps(nb2.cells[i].outputs) == first_outputs and j == i + 2 and 'total' in text2


def test_cli_requires_positional_args(tmp_path, capsys):
    with pytest.raises(SystemExit):
        nbx.main([str(tmp_path / 'n.ipynb'), 'penetration', '--dim', 'seg'])
