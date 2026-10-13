import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export function productionEnvironment(environment) {
  return { ...environment, NODE_ENV: "production" };
}

function build() {
  const directory = fileURLToPath(new URL("../", import.meta.url));
  const environment = productionEnvironment(process.env);
  const steps = [
    ["../node_modules/typescript/bin/tsc", []],
    ["../node_modules/vite/bin/vite.js", ["build"]],
  ];
  for (const [script, args] of steps) {
    const result = spawnSync(process.execPath, [fileURLToPath(new URL(script, import.meta.url)), ...args], {
      cwd: directory, env: environment, stdio: "inherit",
    });
    if (result.error || result.status !== 0) {
      if (result.error) console.error(result.error.message);
      process.exit(result.status ?? 1);
    }
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) build();
