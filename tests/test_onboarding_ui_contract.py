"""Onboarding wiring contracts and executable keyboard/presentation regressions."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"


def test_setup_only_calls_model_on_explicit_check():
    app = (SRC / "DriftApp.tsx").read_text(encoding="utf-8")
    check = app.split("const checkConnection = async () => {", 1)[1].split("const saveToken", 1)[0]
    assert 'fetch("/api/ui/setup/check"' in check
    assert 'method: "POST"' in check and 'body: "{}"' in check
    assert 'headers: authHeaders()' in check and 'if (!res.ok)' in check
    assert app.count('fetch("/api/ui/setup/check"') == 1
    assert 'onCheck={() => { void checkConnection(); }}' in app
    for line in app.splitlines():
        if 'useEffect(' in line or 'setInterval(' in line:
            assert 'checkConnection' not in line
    assert 'fetch("/api/ui/setup", { headers: authHeaders() })' in app


def test_settings_refresh_without_remounting_or_clearing_drafts():
    app = (SRC / "DriftApp.tsx").read_text(encoding="utf-8")
    inbox = (SRC / "ThoughtInbox.tsx").read_text(encoding="utf-8")
    save = app.split('const saveToken = async () => {', 1)[1].split('useEffect', 1)[0]
    assert 'sessionToken.write(token)' in save
    token_store = (SRC / "session-token.ts").read_text(encoding="utf-8")
    assert 'storage().setItem("drift_token", value)' in token_store
    assert 'current = value' in token_store
    assert 'Promise.all([loadStatus(), loadAll(), loadSetup()])' in save
    assert 'setHistoryRevision(value => value + 1)' in save
    assert 'refreshKey={historyRevision}' in app
    assert '[filter.q, filter.offset, organismId, refreshKey]' in inbox
    assert '<ThoughtInbox key=' not in app
    assert 'clearDraft' not in save
    assert 'open={settingsOpen}' in app and 'setSettingsOpen(true)' in app
    assert 'Never enter provider secrets here.' in app
    assert 'setCandidatesUnavailable(!cd)' in app
    assert 'Previously loaded candidates may be stale.' in app


def test_all_tab_panels_have_matching_identifiers():
    app = (SRC / "DriftApp.tsx").read_text(encoding="utf-8")
    for tab in ('status', 'inbox', 'office', 'projects', 'research', 'attention', 'approvals'):
        assert f'id="drift-panel-{tab}" aria-labelledby="drift-tab-{tab}"' in app
    assert 't.id !== tab' in app and 'hidden role="tabpanel"' in app


def test_blank_draft_is_neutral_and_mobile_composer_is_compact():
    inbox = (SRC / "ThoughtInbox.tsx").read_text(encoding="utf-8")
    css = (SRC / "drift.css").read_text(encoding="utf-8")
    assert '!capture.draft.text && !capture.pending ? "Ready for a thought. Nothing to save yet."' in inbox
    assert 'browser draft; use Save to add it to Drift.' in inbox
    assert '@media(max-width:600px)' in css
    assert '.thought-composer textarea{min-height:6rem;height:8rem}' in css
    assert ':focus-visible' in css


def test_keyboard_and_setup_components_execute(tmp_path):
    node = shutil.which('node')
    deps = ROOT / 'frontend' / 'node_modules'
    compiler = deps / 'typescript' / 'lib' / 'typescript.js'
    if not node or not compiler.is_file():
        pytest.skip('Node and installed frontend dependencies required')
    runner = tmp_path / 'onboarding.cjs'
    runner.write_text(r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');
const deps = process.argv[2], src = process.argv[3];
const ts = require(path.join(deps, 'typescript/lib/typescript.js'));
const react = require(path.join(deps, 'react'));
const jsx = require(path.join(deps, 'react/jsx-runtime'));
const server = require(path.join(deps, 'react-dom/server'));
const original = Module._load;
Module._load = function(name, ...rest) {
  if (name === 'react') return {...react, useRef: () => ({current: []})};
  if (name === 'react/jsx-runtime') return jsx;
  return original.call(this, name, ...rest);
};
require.extensions['.tsx'] = function(mod, filename) {
  mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX}
  }).outputText, filename);
};
const Tabs = require(path.join(src, 'SectionTabs.tsx')).default;
const Guide = require(path.join(src, 'SetupGuide.tsx')).default;
let selected, focused, prevented = 0;
const tabs = [{id:'inbox', label:'Inbox'}, {id:'status', label:'Status'}, {id:'office', label:'Office'}];
const tree = Tabs({tabs, selected: 'inbox', onSelect: id => {selected = id;}});
const buttons = tree.props.children;
buttons.forEach((button, i) => button.ref({focus: () => {focused = i;}}));
assert.deepEqual(buttons.map(b => b.props.tabIndex), [0,-1,-1]);
assert.equal(buttons[0].props.id, 'drift-tab-inbox');
assert.equal(buttons[0].props['aria-controls'], 'drift-panel-inbox');
for (const [from, key, to] of [[0,'ArrowLeft',2],[2,'ArrowRight',0],[1,'Home',0],[0,'End',2]]) {
  buttons[from].props.onKeyDown({key, preventDefault: () => {prevented++;}});
  assert.equal(selected, tabs[to].id); assert.equal(focused, to);
}
buttons[0].props.onKeyDown({key:'Tab', preventDefault: () => {throw Error('must not consume Tab');}});
assert.equal(prevented, 4);
let checks = 0;
const props = {error:'', checking:false, onCheck: () => {checks++;}, onSuggestions: () => {}};
const base = {version:'0.2.1', capture_ready:true, storage_path:'C:/scratch/box',
  auth_required:false, free_only:true, shell_enabled:false};
for (const state of ['unchecked','ready','unavailable','limited']) {
  const setup = {...base, processing:{state, message:'Real backend message', model:'gateway-route',
    checked_at: state === 'unchecked' ? null : '2026-10-13T12:00:00Z'}};
  const html = server.renderToStaticMarkup(react.createElement(Guide, {...props, setup}));
  assert.match(html, /Saving ready/); assert.match(html, /C:\/scratch\/box/);
  assert.match(html, /one permitted model call/); assert.match(html, /remote provider/);
  assert.match(html, /No tools or paid fallback/);
  if (state === 'ready') assert.match(html, /does not guarantee the next call/);
}
const missing = server.renderToStaticMarkup(react.createElement(Guide, {...props, setup:null}));
assert.match(missing, /Saving not verified/);
const pending = server.renderToStaticMarkup(react.createElement(Guide, {...props, setup:null, checking:true}));
assert.match(pending, /disabled=""/);
assert.equal(checks, 0, 'rendering guide must never trigger inference');
const guide = Guide({...props, setup:null});
const steps = guide.props.children[1].props.children;
const checkButton = steps[1].props.children.find(child => child && child.type === 'button');
checkButton.props.onClick(); assert.equal(checks, 1, 'explicit button triggers exactly one callback');
console.log('Keyboard wrap/focus/roving tab stops and setup states/cost/privacy/explicit check passed');
''', encoding='utf-8')
    result = subprocess.run([node, str(runner), str(deps), str(SRC)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
