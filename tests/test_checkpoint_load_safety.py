import json
from pathlib import Path
from unittest.mock import patch

import pytest

from drift.task import TaskStore
from drift.organism import DriftLedger


@pytest.mark.parametrize('contents', ['{broken', 'null', '[]', '{"tasks": "broken"}',
                                      '{"tasks": [null]}'])
def test_invalid_task_checkpoint_is_not_an_empty_usable_store(tmp_path, contents):
    path = tmp_path / 'tasks.json'
    path.write_text(contents, encoding='utf-8')
    with pytest.raises((ValueError, TypeError)):
        TaskStore(str(tmp_path))
    assert path.read_text(encoding='utf-8') == contents


def test_transient_task_checkpoint_read_error_preserves_existing_work(tmp_path):
    store = TaskStore(str(tmp_path))
    original = store.create_task('Original task', 'Keep the checkpoint')
    before = store.path.read_bytes()
    read = Path.read_text
    def fail_target(path, *args, **kwargs):
        if path == store.path:
            raise PermissionError('synthetic temporary read failure')
        return read(path, *args, **kwargs)
    with patch.object(Path, 'read_text', fail_target):
        with pytest.raises(OSError):
            TaskStore(str(tmp_path))
    assert store.path.read_bytes() == before
    assert TaskStore(str(tmp_path)).get_task(original.id).goal == 'Original task'


def test_duplicate_task_ids_do_not_silently_replace_work(tmp_path):
    store = TaskStore(str(tmp_path))
    task = store.create_task('Original task', 'Keep the checkpoint')
    data = {'schema': 1, 'tasks': [task.to_dict(), {**task.to_dict(), 'goal': 'Replacement'}]}
    store.path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        TaskStore(str(tmp_path))


@pytest.mark.parametrize('contents', ['{broken', 'null', '[]', '{}',
                                      '{"ideas": "broken"}', '{"mind_map": []}'])
def test_invalid_ledger_cannot_be_reopened_and_overwritten(tmp_path, contents):
    path = tmp_path / 'drift_ledger.json'
    path.write_text(contents, encoding='utf-8')
    with pytest.raises((ValueError, TypeError)):
        DriftLedger(str(tmp_path))
    assert path.read_text(encoding='utf-8') == contents


def test_transient_ledger_read_error_refuses_mutation_without_losing_memory(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    original = ledger.add_idea('Original idea')
    before = ledger.path.read_bytes()
    read = Path.read_text
    def fail_target(path, *args, **kwargs):
        if path == ledger.path:
            raise PermissionError('synthetic temporary read failure')
        return read(path, *args, **kwargs)
    with patch.object(Path, 'read_text', fail_target):
        with pytest.raises(OSError):
            ledger.add_idea('Must not replace original')
    assert ledger.path.read_bytes() == before
    assert ledger.data['ideas'][0]['id'] == original.id
    assert DriftLedger(str(tmp_path)).data['ideas'][0]['text'] == 'Original idea'


def test_direct_ledger_save_refuses_to_overwrite_newly_corrupt_checkpoint(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    ledger.add_idea('Retained idea')
    ledger.path.write_text('{damaged', encoding='utf-8')
    with pytest.raises(ValueError):
        ledger.save()
    assert ledger.path.read_text(encoding='utf-8') == '{damaged'


@pytest.mark.parametrize('schema', [True, 1.0])
def test_task_schema_version_must_be_an_integer(tmp_path, schema):
    path = tmp_path / 'tasks.json'
    path.write_text(json.dumps({'schema': schema, 'tasks': []}), encoding='utf-8')
    before = path.read_bytes()
    with pytest.raises(ValueError):
        TaskStore(str(tmp_path))
    assert path.read_bytes() == before


@pytest.mark.parametrize('key,record', [('nodes', None), ('nodes', {}),
                                      ('edges', None), ('edges', {})])
def test_invalid_graph_records_are_not_reloaded_or_persisted(tmp_path, key, record):
    ledger = DriftLedger(str(tmp_path))
    ledger.add_idea('Keep this idea')
    data = json.loads(ledger.path.read_text(encoding='utf-8'))
    data['mind_map'][key] = [record]
    ledger.path.write_text(json.dumps(data), encoding='utf-8')
    before = ledger.path.read_bytes()
    with pytest.raises(ValueError):
        ledger.add_idea('Do not persist over invalid state')
    assert ledger.path.read_bytes() == before
