"""Derive credential-filtered inference parts from the canonical full original."""
from drift.capture_store import CaptureStore
from drift.intake import CHUNK_CHARS
from drift.privacy import redact_slice, redact_text


def capture_source(root, task):
    if not task.capture_id:
        return redact_text(task.source_text)
    capture = CaptureStore(root).get(task.capture_id)
    if not capture:
        raise ValueError('Canonical capture unavailable; withholding model context')
    start = task.part_index * CHUNK_CHARS
    end = start + len(task.source_text)
    if capture['text'][start:end] != task.source_text:
        raise ValueError('Capture checkpoint differs from original; withholding model context')
    return redact_slice(capture['text'], start, end)
