import json

import pytest

from drift.brain import Brain
from drift.capture_store import CaptureStore
from drift.intake import CHUNK_CHARS, stage_captures
from drift.memory import MemoryStream
from drift.privacy import redact_text


@pytest.mark.parametrize('quote', ['"', "'"])
def test_quoted_multiword_credentials_are_fully_redacted(quote):
    original = f'password={quote}two synthetic words{quote}; keep the surrounding thought'
    safe = redact_text(original)
    assert 'two' not in safe and 'synthetic words' not in safe
    assert '[REDACTED]' in safe
    assert 'keep the surrounding thought' in safe


def test_escaped_quote_inside_password_cannot_end_redaction_early():
    safe = redact_text('password="two \\"synthetic\\" words"; continue thinking')
    assert 'synthetic' not in safe and 'words' not in safe
    assert 'continue thinking' in safe


def test_chunk_boundary_redaction_uses_full_original_without_rewriting_parts(tmp_path):
    original = 'x' * (CHUNK_CHARS - 9) + ' ' + 'sk-' + 'A' * 32 + ' thought continues'
    capture = CaptureStore(tmp_path).capture(original)['capture']
    brain = Brain({'name': 'privacy'}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path)); brain._init_stores()
    stage_captures(brain, max_tasks=1)
    reopened = Brain({'name': 'privacy'}, str(tmp_path))
    reopened.stream = MemoryStream(str(tmp_path)); reopened._init_stores()
    stage_captures(reopened, max_tasks=1)
    parts = sorted([t for t in reopened.tasks.list_tasks() if t.capture_id == capture['id']], key=lambda t: t.part_index)
    assert ''.join(t.source_text for t in parts) == original
    payloads = []
    for task in parts:
        _, inputs, _ = reopened._build_task_context(task)
        payloads.append(json.loads(next(i['content'] for i in inputs if 'original_thought_part' in i['content']))['original_thought_part'])
    combined = ''.join(payloads)
    assert 'sk-' not in combined
    assert 'A' * 27 not in combined
    assert 'thought continues' in combined
    assert CaptureStore(tmp_path).get(capture['id'])['text'] == original


def test_projection_redacts_before_truncating_a_long_original(tmp_path):
    original = 'x' * 3989 + ' ' + 'sk-' + 'A' * 32 + ' preserved tail'
    capture = CaptureStore(tmp_path).capture(original)['capture']
    brain = Brain({'name': 'privacy'}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path)); brain._init_stores()
    stage_captures(brain, max_tasks=1)
    idea = next(i for i in brain.ledger.data['ideas'] if i.get('capture_id') == capture['id'])
    assert 'sk-' not in idea['text']
    assert CaptureStore(tmp_path).get(capture['id'])['text'] == original
