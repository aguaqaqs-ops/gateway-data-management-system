import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { buildSourcePackage } from "../src/features/workbench/upload-package.ts";

const output = process.argv[2];
if (!output) throw new Error("usage: build-upload-validation-fixtures.mjs <output-dir>");
await mkdir(output, { recursive: true });

const PM = "station.pmc";
const SQL = "sql/dbcfg.sql";
const XML = "comps/logic/logics.xml";
const LONG = `comps/${"very-long-directory-segment-".repeat(4)}nested/logics.xml`;

function directory(name, files) {
  const entries = files.map(([path, content]) => ({ path, file: new File([content], path.split("/").at(-1) ?? "file", { type: "text/plain" }) }));
  return {
    rootName: name,
    files: entries,
    totalBytes: entries.reduce((sum, entry) => sum + entry.file.size, 0),
    mainFile: PM,
  };
}

const cases = [
  { name: "with-logics", expect: "accepted", files: [[PM, "pmc-v1\n"], [SQL, "create table device(id int);\n"], [XML, "<logics version=\"1\"/>\n"]] },
  { name: "without-logics", expect: "accepted", files: [[PM, "pmc-v1\n"], [SQL, "create table device(id int);\n"]] },
  { name: "missing-dbcfg", expect: "UPLOAD_CLOSURE_INVALID", files: [[PM, "pmc-v1\n"], [XML, "<logics/>\n"]] },
  { name: "long-path", expect: "accepted", files: [[PM, "pmc-v1\n"], [SQL, "create table device(id int);\n"], [LONG, "<long/>\n"]] },
];

const manifest = [];
for (const item of cases) {
  if (Buffer.byteLength(LONG, "utf8") <= 100) throw new Error("long path fixture must exceed 100 bytes");
  const file = await buildSourcePackage(directory(item.name, item.files));
  await writeFile(join(output, `${item.name}.tar.gz`), Buffer.from(await file.arrayBuffer()));
  manifest.push({
    name: item.name,
    expect: item.expect,
    members: item.files.map(([path, content]) => ({ path, size: Buffer.byteLength(content), sha256: createHash("sha256").update(content).digest("hex") })).sort((left, right) => left.path.localeCompare(right.path)),
  });
}
await writeFile(join(output, "manifest.json"), `${JSON.stringify({ packages: manifest }, null, 2)}\n`);
console.log(`built ${manifest.length} upload validation packages in ${output}`);
