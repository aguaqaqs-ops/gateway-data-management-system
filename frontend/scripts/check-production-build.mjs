import { access, readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

const assets = join(process.cwd(), "dist", "assets");
const moduleManifestPath = join(process.cwd(), "node_modules", ".cache", "frontend-build", "production-modules.json");
const leakedManifestPath = join(process.cwd(), "dist", ".vite", "rollup-modules.json");
try {
  await access(leakedManifestPath);
  process.stderr.write("production dist includes the build module manifest: dist/.vite/rollup-modules.json\n");
  process.exit(1);
} catch {
  // Expected: the manifest must live outside dist.
}
const moduleManifest = JSON.parse(await readFile(moduleManifestPath, "utf8"));
const developmentModules = moduleManifest.filter((id) => /\/src\/features\/dev\//.test(id.replaceAll("\\", "/")));
if (developmentModules.length) {
  process.stderr.write("production dist includes development-only modules:\n" + developmentModules.join("\n") + "\n");
  process.exit(1);
}
const files = await readdir(assets);
const forbidden = [
  /fe2a-fixture/i,
  /simulated[-_ ]api/i,
  /GatewaySimulatedApiModule/,
  /identity[-_ ]selector/i,
  /模拟身份|dev-token-(?:submitter|reviewer|archive-confirmer|no-permission)/,
  /mock[-_ ]identity/i,
  /__gatewayTestConfig/,
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
process.stdout.write("production dist contains no simulated API, identity selection, or mock data modules\n");
