import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";

const require = createRequire(import.meta.url);
const { build } = require("esbuild");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

test("connection loss labels unchanged active work offline, reconnection restores live", async () => {
  const result = await build({
    entryPoints: [fileURLToPath(new URL("../src/office/DeskView.tsx", import.meta.url))],
    bundle: true,
    write: false,
    platform: "node",
    format: "cjs",
    external: ["react", "react-dom"],
    loader: { ".css": "empty" },
    logLevel: "silent",
  });
  const module = { exports: {} };
  new Function("require", "module", "exports", result.outputFiles[0].text)(require, module, module.exports);
  const project = { id: "connection-test-project", name: "Connection regression project" };
  const task = { id: "connection-test-task", status: "running", goal: "Preserve the cached task", source_text: "Original saved task content" };
  const work = { mode: "live", kind: "writing", task, project, target: "cached-target.txt" };
  const before = JSON.stringify(work);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = () => { throw new Error("SSR must not contact any service"); };
  try {
    for (const connected of [true, false, true]) {
      const html = renderToStaticMarkup(React.createElement(module.exports.default, {
        work, project, connected, headers: () => ({}), onProject() {}, onReport() {},
      }));
      assert.ok(html.includes(task.source_text), "cached task content stays visible");
      assert.ok(html.includes(project.name), "cached project stays visible");
      assert.ok(html.includes(work.target), "observed target stays visible");
      assert.equal(JSON.stringify(work), before, "connection state does not mutate cached work");
      if (connected) {
        assert.match(html, /LIVE WORK/);
        assert.doesNotMatch(html, /OFFLINE/);
      } else {
        assert.doesNotMatch(html, /LIVE WORK/, "disconnected work must not be labelled live");
        assert.match(html, /OFFLINE.*LAST KNOWN/);
      }
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});
