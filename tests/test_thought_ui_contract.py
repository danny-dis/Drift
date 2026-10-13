"""New thought UI contracts plus executable, dependency-free capture-store tests."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"


def test_capture_and_history_are_accessible_and_keep_originals():
    ui = (SRC / "ThoughtInbox.tsx").read_text(encoding="utf-8")
    css = (SRC / "thoughts.css").read_text(encoding="utf-8")
    for needle in ('aria-live', '<label', '<textarea', 'metaKey', 'ctrlKey',
                   'Clear draft', 'Saved locally', 'original', 'has_more',
                   'offset', 'encodeURIComponent', 'needs_review'):
        assert needle in ui
    assert 'dangerouslySetInnerHTML' not in ui
    assert 'maxLength' not in ui
    assert 'prefers-reduced-motion' in css
    assert 'overflow-wrap' in css
    assert ':focus-visible' in css


def test_capture_store_runtime_preserves_drafts_and_retry_identity(tmp_path):
    source = SRC / "useThoughtCapture.ts"
    assert source.is_file(), "Capture store must exist"
    node = shutil.which("node")
    candidates = [ROOT / "frontend/node_modules/typescript/lib/typescript.js"]
    configured = os.environ.get("DRIFT_TEST_TYPESCRIPT")
    if configured:
        candidates.insert(0, Path(configured))
    candidates.extend((Path(os.environ.get("LOCALAPPDATA", "")) / "Temp").glob(
        "drift-audit-*/frontend/node_modules/typescript/lib/typescript.js"))
    compiler = next((path for path in candidates if path.is_file()), None)
    if not node or not compiler:
        pytest.skip("Node and TypeScript required for executable frontend contracts")
    runner = tmp_path / "capture-contract.cjs"
    runner.write_text(r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');
const ts = require(process.argv[2]);
const base = process.argv[3];
const original = Module._load;
Module._load = function(name, ...rest) {
  if (name === 'react') return {};
  return original.call(this, name, ...rest);
};
require.extensions['.ts'] = function(mod, filename) {
  mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
  }).outputText, filename);
};
const { createThoughtCaptureStore } = require(path.join(base, 'useThoughtCapture.ts'));
const { MAX_CAPTURE_LENGTH } = require(path.join(base, 'thought-types.ts'));
const memory = new Map();
const storage = { getItem: k => memory.get(k) ?? null,
  setItem: (k, v) => memory.set(k, v), removeItem: k => memory.delete(k) };
let count = 0, calls = [], resolve;
const dependencies = { storage, newId: () => `id-${++count}`,
  request: (url, init) => { calls.push({url, init});
    return new Promise(done => { resolve = done; }); } };
const ok = text => ({ ok: true, json: async () => ({capture: {
  id: 'server-id', text, status: 'captured', created_at: '2026-10-13',
  idea_id: null, task_id: null, report_path: null }, deduplicated: false}) });
(async () => {
  let store = createThoughtCaptureStore(() => ({Authorization: 'Bearer test'}), 'one', dependencies);
  const text = '  typos r fine\nsecond line 🦊  ';
  store.setText(text);
  const firstId = store.getSnapshot().draft.client_id;
  store.setText(text);
  assert.equal(store.getSnapshot().draft.client_id, firstId);
  store = createThoughtCaptureStore(() => ({}), 'one', dependencies);
  assert.equal(store.getSnapshot().draft.text, text);
  assert.equal(store.getSnapshot().draft.client_id, firstId);
  const sending = store.capture();
  await store.capture();
  assert.equal(calls.length, 1, 'busy guard prevents duplicate POST');
  assert.deepEqual(JSON.parse(calls[0].init.body), {text, client_id: firstId});
  store.setText('a newer thought');
  assert.notEqual(store.getSnapshot().draft.client_id, firstId);
  resolve(ok(text)); await sending;
  assert.equal(store.getSnapshot().draft.text, 'a newer thought', 'late success cannot clear newer draft');
  const failing = store.capture();
  resolve({ok: false, status: 503}); await failing;
  const failed = store.getSnapshot();
  assert.equal(failed.draft.text, 'a newer thought');
  assert.equal(failed.pending.client_id, failed.draft.client_id);
  store = createThoughtCaptureStore(() => ({}), 'one', dependencies);
  const retry = store.capture();
  assert.equal(calls[1].init.body, calls[2].init.body, 'retry after reload uses exact payload');
  resolve(ok('a newer thought')); await retry;
  assert.equal(store.getSnapshot().draft.text, '');
  assert.equal(store.getSnapshot().pending, null);
  store.setText('offline original');
  const offline = store.capture();
  store.setText('keep typing during offline request');
  resolve({ok: false, status: 503}); await offline;
  store = createThoughtCaptureStore(() => ({}), 'one', dependencies);
  assert.equal(store.getSnapshot().draft.text, 'keep typing during offline request');
  assert.equal(store.getSnapshot().pending.text, 'offline original');
  const earlier = store.capture();
  resolve(ok('offline original')); await earlier;
  assert.equal(store.getSnapshot().draft.text, 'keep typing during offline request');
  const isolated = createThoughtCaptureStore(() => ({}), 'two', dependencies);
  assert.equal(isolated.getSnapshot().draft.text, '');
  store.clearDraft();
  assert.equal(store.getSnapshot().draft.text, '');
  const before = calls.length;
  store.setText('x'.repeat(MAX_CAPTURE_LENGTH + 1));
  await store.capture();
  assert.equal(calls.length, before, 'explicit server limit does not send oversized input');
  assert.match(store.getSnapshot().error, /1,000,000/);
  const brokenStorage = {getItem() { throw Error('blocked'); },
    setItem() { throw Error('quota'); }, removeItem() { throw Error('blocked'); }};
  const unavailable = createThoughtCaptureStore(() => ({}), 'blocked', {...dependencies, storage: brokenStorage});
  unavailable.setText('still editable');
  assert.equal(unavailable.getSnapshot().draft.text, 'still editable');
  assert.equal(unavailable.getSnapshot().locallySaved, false);
  console.log('Capture runtime: persistence, identity, busy guard, race, retry, scope, limit, storage failure passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
''', encoding="utf-8")
    result = subprocess.run([node, str(runner), str(compiler), str(SRC)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
