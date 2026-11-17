import { AlertTriangle } from "lucide-react";
import {
  formatNavigationDiagnostic,
  type NavigationDiagnostic,
} from "../../features/view-model/diagnostics";
import type { SurfaceTable } from "../../features/view-model/model";

export function NavigationDiagnosticNote({
  diagnostic,
  tables,
  debug,
  onOpenWholeTable,
  onBrowseUnassigned,
  canBrowseUnassigned,
}: {
  diagnostic: NavigationDiagnostic;
  tables: readonly SurfaceTable[];
  debug: boolean;
  onOpenWholeTable: (tableName: string, itemKey?: string | null) => void;
  onBrowseUnassigned: (tableName: string, side: "BEFORE" | "CURRENT") => void;
  canBrowseUnassigned: (diagnostic: NavigationDiagnostic) => boolean;
}) {
  const message = formatNavigationDiagnostic(diagnostic, tables);
  const orphan =
    diagnostic.code === "DEVICE_ROWS_UNASSIGNED" && Boolean(diagnostic.target.table_id);
  const browsable = orphan && canBrowseUnassigned(diagnostic);
  return (
    <div className="diagnostic-note diagnostic-note--navigation">
      <AlertTriangle size={14} />
      <span>
        {message}
        {orphan && !browsable && (
          <small className="diagnostic-note__hint">
            （无法按装置条件筛出未归属行，请查看整表）
          </small>
        )}
      </span>
      {orphan && (
        <button
          onClick={() =>
            onOpenWholeTable(diagnostic.target.table_id as string, diagnostic.target.item_key)
          }
        >
          查看整表
        </button>
      )}
      {browsable && diagnostic.side && (
        <button
          onClick={() =>
            onBrowseUnassigned(
              diagnostic.target.table_id as string,
              diagnostic.side as "BEFORE" | "CURRENT",
            )
          }
        >
          浏览未归属行
        </button>
      )}
      {debug && (
        <code>
          {JSON.stringify({
            code: diagnostic.code,
            target: diagnostic.target,
            side: diagnostic.side,
            params: diagnostic.params,
          })}
        </code>
      )}
    </div>
  );
}
