// Runs the official Meterless H-MEM conformance runner (conformance/runner.ts,
// Apache-2.0, meterless/meterless@1742dec) against this engine (src/index.ts)
// and saves the scorecard to conformance/results/hmem.txt.
//
//   npm --prefix engines/hmem run conformance

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const impl = path.join(root, "src", "index.ts");
const runner = path.join(root, "conformance", "runner.ts");
const r = spawnSync(process.execPath, [runner], {
  cwd: path.dirname(runner),
  env: { ...process.env, HMEM_IMPL: impl },
  encoding: "utf-8",
});
const out = `${r.stdout ?? ""}${r.stderr ?? ""}`;
process.stdout.write(out);
const resultsDir = path.join(root, "conformance", "results");
fs.mkdirSync(resultsDir, { recursive: true });
fs.writeFileSync(path.join(resultsDir, "hmem.txt"), `$ HMEM_IMPL=src/index.ts node conformance/runner.ts\n# ${new Date().toISOString()}\n${out}`);
process.exit(r.status ?? 1);
