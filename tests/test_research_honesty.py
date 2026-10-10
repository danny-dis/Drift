"""Citation honesty, crash recovery and decision wiring regressions."""
import pytest
from drift.research import ResearchStore
from drift.config import config
from drift.memory import MemoryStream


def test_known_source_does_not_verify_fabricated_quote(tmp_path):
    store = ResearchStore(str(tmp_path))
    session = store.start('What does pathlib do?')
    source = store.add_source(session['id'], 'https://docs.python.org/3/library/pathlib.html',
                              'According to the documentation, pathlib provides object-oriented filesystem paths.')
    result = store.finish(session['id'], {'findings': ['All filesystem paths are automatically sandboxed.'],
        'citations': [{'source_id': source['id'], 'quote': 'all paths are automatically sandboxed'}]})
    assert result['verified'] is False
    assert result['state'] == 'needs_review'


def test_uncited_findings_stay_unverified(tmp_path):
    store = ResearchStore(str(tmp_path)); session = store.start('What does pathlib do?')
    store.add_source(session['id'], 'https://docs.python.org/3/library/pathlib.html', 'Pathlib is a Python module.')
    result = store.finish(session['id'], {'findings': ['The library secures every application.'], 'citations': []})
    assert result['verified'] is False


def test_research_restart_not_blocked_by_abandoned_lock_directory(tmp_path):
    (tmp_path / '.lock').mkdir()  # previous process crashed in its mkdir-lock
    result = ResearchStore(str(tmp_path)).start('Restart this research')
    assert ResearchStore(str(tmp_path)).get(result['id'])['query'] == 'Restart this research'


def test_memory_calls_one_batched_decider_and_persists_metadata(tmp_path, monkeypatch):
    import drift.memory as module
    assert hasattr(module, 'decide_memory')
    calls = []
    def decide(text, **kwargs):
        calls.append(text)
        return {'importance': 3, 'importance_display': 4, 'kind': 'lesson', 'retain': True,
                'retention': 'normal', 'provider': 'fixture', 'confidence': 0.8,
                'fallback': None, 'latency_ms': 0}
    monkeypatch.setattr(module, 'decide_memory', decide)
    entry = MemoryStream(str(tmp_path)).add('A real lesson about persistence')
    assert len(calls) == 1
    assert entry['importance'] == 4
    assert MemoryStream(str(tmp_path)).get_recent()[0]['decision']['kind'] == 'lesson'


def test_corrupt_budget_cannot_reopen_admission(tmp_path):
    from drift.providers import CallBudget
    (tmp_path / 'call_budget.json').write_text('{corrupted', encoding='utf-8')
    with pytest.raises((ValueError, RuntimeError)):
        CallBudget(str(tmp_path)).can_call()
    assert (tmp_path / 'call_budget.json').read_text(encoding='utf-8') == '{corrupted'
