from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_blocked_session_storage_does_not_prevent_dashboard_render(tmp_path):
    node = shutil.which("node")
    compiler = ROOT / "frontend/node_modules/typescript/lib/typescript.js"
    if not node or not compiler.is_file():
        pytest.skip("Node and locked frontend dependencies are required")
    script = r'''
const assert = require("node:assert/strict"), fs = require("node:fs"), path = require("node:path"), Module = require("node:module");
const ts = require(process.argv[2]), root = process.argv[3], cache = new Map();
const react = {...require(path.resolve(root,"../node_modules/react")),useState(value){return [typeof value === "function" ? value() : value,()=>{}]},useRef(value){return {current:value}},useMemo(fn){return fn()},useCallback(fn){return fn},useEffect(){},useId(){return "test"},createElement(type,props,...children){return {type,props:props||{},children}}};
function load(file){
  if(file.endsWith(".css")) return {};
  if(cache.has(file)) return cache.get(file).exports;
  const m = new Module(file); cache.set(file,m);
  m.require = name => {
    if(name === "react") return react;
    if(name === "react/jsx-runtime") return {jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
    if(name.startsWith(".")) {
      const stem = path.resolve(path.dirname(file),name);
      const target = [stem,stem+".ts",stem+".tsx"].find(candidate=>fs.existsSync(candidate));
      return load(target);
    }
    return require(name);
  };
  m._compile(ts.transpileModule(fs.readFileSync(file,"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2020}}).outputText,file);
  return m.exports;
}
Object.defineProperty(global,"sessionStorage",{get(){throw new Error("Storage blocked for test")}});
assert.equal(load(path.join(root,"DriftApp.tsx")).default().type,"main");
console.log("dashboard remains renderable with session storage blocked");
'''
    target = tmp_path / "storage.cjs"
    target.write_text(script, encoding="utf-8")
    result = subprocess.run([node, str(target), str(compiler), str(ROOT / "frontend/src")], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
