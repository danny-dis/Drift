import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";

const require = createRequire(import.meta.url);
const { build } = require("esbuild");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

async function render(name, props) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(`../src/${name}.tsx`, import.meta.url))],
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
  return renderToStaticMarkup(React.createElement(module.exports.default, props));
}

test("non-office initial states render without service calls or expanded technical details", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = () => {
    calls++;
    throw new Error("Initial rendering must not contact Drift or an AI provider");
  };
  try {
    const cases = [
      ["SetupGuide", { setup: null, error: "", checking: false, onCheck() {}, onSuggestions() {} }, "AI not checked"],
      ["ThoughtInbox", { headers: () => ({}), onCaptured() {} }, "Save thought"],
      ["ThoughtInsights", { captureId: "synthetic-ui-check", status: "saved", headers: () => ({}) }, "Loading saved suggestions"],
      ["BudgetSummary", { value: {} }, "allowance is unavailable"],
      ["ProjectIntelligence", { projectId: "synthetic-ui-check", headers: () => ({}), publishAvailable: false }, "No internal project briefing yet"],
    ];
    for (const [name, props, expected] of cases) {
      const html = await render(name, props);
      assert.ok(html.includes(expected), `${name} provides its initial or unavailable state`);
      assert.ok(!/<details\b[^>]*\bopen(?:[\s=>])/.test(html), `${name} starts with technical details collapsed`);
    }
    assert.equal(calls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
