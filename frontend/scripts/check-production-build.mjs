import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

const assets = join(process.cwd(), "dist", "assets");
const files = await readdir(assets);
const forbidden = [
  /fe2a-fixture/i,
  /simulated[-_ ]api/i,
  /GatewaySimulatedApiModule/,
  /identity[-_ ]selector/i,
  /模拟身份|dev-token-(?:submitter|reviewer|archive-confirmer|no-permission)/,
  /mock[-_ ]identity/i,
];
const violations = [];
for (const name of files) {
  const source = await readFile(join(assets, name), "utf8");
  for (const pattern of forbidden) if (pattern.test(source)) violations.push(name + ": " + pattern);
}
if (violations.length) {
  process.stderr.write("production dist contains development simulation code:\n" + violations.join("\n") + "\n");
  process.exit(1);
}
process.stdout.write("production dist contains no simulated API or identity selection code\n");
