import { parquetReadObjects, type AsyncBuffer, type ParquetRow } from "hyparquet";
import { compressors } from "hyparquet-compressors";
import type { InstalledBundle } from "./local-bundle";

export interface ParquetReadRequest {
  columns?: string[];
  rowStart?: number;
  rowEnd?: number;
}

/** Reads a table only from the installed local bundle; it has no API client or network path. */
export async function readParquetTable(
  bundle: InstalledBundle,
  logicalPath: string,
  request: ParquetReadRequest = {},
): Promise<ParquetRow[]> {
  const read = async (current: InstalledBundle) => {
    const blob = await current.readArtifact(logicalPath);
    const file: AsyncBuffer = {
      byteLength: blob.size,
      slice: async (start, end) => blob.slice(start, end).arrayBuffer(),
    };
    return parquetReadObjects({
      file,
      columns: request.columns,
      rowStart: request.rowStart,
      rowEnd: request.rowEnd,
      compressors,
    });
  };
  return bundle.readWithRetry ? bundle.readWithRetry(read) : read(bundle);
}

export async function readJsonArtifact<T>(bundle: InstalledBundle, logicalPath: string): Promise<T> {
  const read = async (current: InstalledBundle) => JSON.parse(await (await current.readArtifact(logicalPath)).text()) as T;
  return bundle.readWithRetry ? bundle.readWithRetry(read) : read(bundle);
}
