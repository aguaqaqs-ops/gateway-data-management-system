import { describe, expect, it } from "vitest";
import { buildSourcePackage, buildTar, collectLocalDirectory, type LocalDirectory } from "./upload-package";

function withRelativePath(file: File, path: string): File {
  Object.defineProperty(file, "webkitRelativePath", { value: path });
  return file;
}

function directoryFile(path: string, content = "x"): File {
  const relative = path.split("/");
  return withRelativePath(new File([content], relative.at(-1) ?? path), path);
}

function validInput(root = "station_cfg"): File[] {
  return [
    directoryFile(`${root}/station.pmc`, "pmc"),
    directoryFile(`${root}/sql/dbcfg.sql`, "sql"),
    directoryFile(`${root}/comps/logic/logics.xml`, "xml"),
  ];
}

describe("collectLocalDirectory", () => {
  it("normalizes one selected root and records the main file", () => {
    const result = collectLocalDirectory(validInput());
    expect(result.errors).toEqual([]);
    expect(result.directory?.rootName).toBe("station_cfg");
    expect(result.directory?.mainFile).toBe("station.pmc");
    expect(result.directory?.files.map((file) => file.path)).toEqual([
      "comps/logic/logics.xml",
      "sql/dbcfg.sql",
      "station.pmc",
    ]);
  });

  it("reports every directory rule violation in one list", () => {
    const result = collectLocalDirectory([
      directoryFile("station/system.pmc"),
      directoryFile("station/extra.pmc"),
    ]);
    expect(result.directory).toBeNull();
    expect(result.errors).toEqual([
      "根目录下必须恰好存在一个 .pmc 文件",
      "目录中必须存在 sql/dbcfg.sql",
    ]);
  });

  it("rejects selecting more than one root directory", () => {
    const result = collectLocalDirectory([...validInput("one"), directoryFile("two/sql/dbcfg.sql")]);
    expect(result.errors).toEqual(["只能选择一个根目录"]);
  });

  it("rejects directories above the file count budget", () => {
    const files = [directoryFile("station/station.pmc"), directoryFile("station/sql/dbcfg.sql")];
    for (let index = 0; index < 5000; index += 1) files.push(directoryFile(`station/data/${index}.txt`));
    const result = collectLocalDirectory(files);
    expect(result.directory).toBeNull();
    expect(result.errors).toContain("文件数量不能超过 5000 个");
  });
});

describe("buildTar", () => {
  it("writes deterministic ustar headers in path order", async () => {
    const directory = collectLocalDirectory(validInput()).directory;
    expect(directory).not.toBeNull();
    const first = await buildTar(directory as LocalDirectory);
    const second = await buildTar(directory as LocalDirectory);
    expect(Array.from(first)).toEqual(Array.from(second));
    const name = new TextDecoder().decode(first.subarray(0, 100)).replace(/\0.*$/, "");
    expect(name).toBe("comps/logic/logics.xml");
    const mode = new TextDecoder().decode(first.subarray(100, 108));
    expect(mode).toBe("0000644\0");
    const mtime = new TextDecoder().decode(first.subarray(136, 148));
    expect(mtime).toBe("00000000000\0");
  });

  it("refuses paths that escape the archive root", async () => {
    const directory: LocalDirectory = {
      rootName: "station",
      totalBytes: 1,
      mainFile: "station.pmc",
      files: [{ path: "../secret", file: new File(["x"], "secret") }],
    };
    await expect(buildTar(directory)).rejects.toThrow("目录中的文件路径不安全");
  });

  it("gzip packages the archive with the directory name", async () => {
    const directory = collectLocalDirectory(validInput()).directory;
    const pkg = await buildSourcePackage(directory as LocalDirectory);
    expect(pkg.name).toBe("station_cfg.tar.gz");
    expect(pkg.type).toBe("application/gzip");
    const raw = new Uint8Array(await pkg.arrayBuffer());
    expect(raw[0]).toBe(0x1f);
    expect(raw[1]).toBe(0x8b);
  });
});
