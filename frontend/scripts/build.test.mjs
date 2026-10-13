import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";


test("build script uses the explicit production wrapper", async () => {
  const value = JSON.parse(await readFile(new URL("../package.json", import.meta.url)));
  assert.equal(value.scripts.build, "node scripts/build.mjs");
});


test("production environment overrides inherited development without dropping other variables", async () => {
  const { productionEnvironment } = await import("./build.mjs");
  const original = { NODE_ENV: "development", KEEP: "unchanged" };
  assert.deepEqual(productionEnvironment(original), { NODE_ENV: "production", KEEP: "unchanged" });
  assert.equal(original.NODE_ENV, "development");
});
