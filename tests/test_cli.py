"""End-to-end: both CLIs run on the session sandbox and write a readout whose close has all five lines."""
import sys

import pytest

from monaco import cli_funnel, cli_partner_health
from monaco.readout import CLOSE_KEYS

LABELS = {'headline': '**Headline:**', 'decision': '**Go / No-go:**', 'action': '**Action:**', 'guardrail': '**Guardrail:**', 'revisit': '**Revisit:**'}


def _run(main, argv, monkeypatch):
    monkeypatch.setattr(sys, 'argv', argv)
    main()


@pytest.mark.parametrize('name,main,extra', [
    ('funnel', cli_funnel.main, ['--min-n', '20', '--top', '6']),
    ('partner_health', cli_partner_health.main, ['--min-n', '20', '--as-of', '2026-10-22']),
])
def test_cli_writes_readout_with_full_close(sandbox_db, tmp_path, monkeypatch, name, main, extra):
    out = tmp_path / name
    _run(main, [f'monaco-{name}', '--db', str(sandbox_db), '--out', str(out), *extra], monkeypatch)
    text = (out / 'readout.md').read_text()
    for k in CLOSE_KEYS:
        assert LABELS[k] in text
    assert '[TODO]' not in text, 'the CLIs draft every close line; a TODO means a code path skipped one'
    assert any((out / 'figs').glob('*.png')) and any((out / 'tables').glob('*.csv'))
