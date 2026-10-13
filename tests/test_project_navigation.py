from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_map_project_selection_resolves_only_real_project_ids(tmp_path):
    node = shutil.which("node")
    compiler = ROOT / "frontend/node_modules/typescript/lib/typescript.js"
    if not node or not compiler.is_file():
        pytest.skip("Node and frontend dependencies required")
    script = tmp_path / "map.cjs"
    script.write_text("""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const ts = require(process.argv[2]);
const mod = new Module(process.argv[3]);
mod._compile(ts.transpileModule(fs.readFileSync(process.argv[3], 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}
}).outputText, process.argv[3]);
const projects = [{id:'one',name:'First'},{id:'two',name:'Second'}];
const resolve = mod.exports.projectForNode;
assert.equal(resolve('p:one',projects),projects[0]);
assert.equal(resolve('p:two',projects),projects[1]);
assert.equal(resolve('i:one',projects),undefined);
assert.equal(resolve('p:missing',projects),undefined);
assert.equal(resolve('one',projects),undefined);
""", encoding="utf-8")
    result = subprocess.run([node, str(script), str(compiler), str(ROOT / "frontend/src/project-navigation.ts")], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
