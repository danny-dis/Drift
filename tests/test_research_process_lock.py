"""Research writers in distinct processes must not overlap or lose updates."""
import os
from pathlib import Path
import subprocess
import sys
import time

from drift.research import ResearchStore


def test_research_writers_wait_for_other_process(tmp_path):
    store = ResearchStore(str(tmp_path))
    store._acquire()
    ready = tmp_path / 'ready'
    acquired = tmp_path / 'acquired'
    code = """
import sys
from pathlib import Path
from drift.research import ResearchStore
root = Path(sys.argv[1])
store = ResearchStore(str(root))
(root / 'ready').write_text('ready')
store._acquire()
try:
    (root / 'acquired').write_text('acquired')
finally:
    store._release()
"""
    child = subprocess.Popen([sys.executable, '-c', code, str(tmp_path)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 30
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert ready.exists(), 'child did not reach acquisition'
        time.sleep(.2)
        assert not acquired.exists(), 'two processes held the research write lock'
    finally:
        store._release()
        try:
            stdout, stderr = child.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            raise
    assert child.returncode == 0, stderr.decode(errors='replace')
    assert acquired.exists()


def test_concurrent_process_source_updates_survive_restart(tmp_path):
    store = ResearchStore(str(tmp_path))
    session = store.start('Concurrent source retention')
    code = """
import sys
from drift.research import ResearchStore
store = ResearchStore(sys.argv[1])
for index in range(4):
    store.add_source(sys.argv[2], 'https://example.com/' + sys.argv[3] + str(index),
                     'Retained source ' + sys.argv[3] + str(index))
"""
    children = [subprocess.Popen([sys.executable, '-c', code, str(tmp_path), session['id'], name],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                for name in ('a', 'b')]
    try:
        for child in children:
            _, stderr = child.communicate(timeout=40)
            assert child.returncode == 0, stderr.decode(errors='replace')
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate()
    result = ResearchStore(str(tmp_path)).get(session['id'])
    assert len(result['sources']) == 8
    assert result['rev'] == 9
