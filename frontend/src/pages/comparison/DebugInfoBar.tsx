import { Copy } from "lucide-react";
import { useEffect, useState } from "react";
import type { SurfaceTable } from "../../features/view-model/model";

export type RiskReasonDetail = { reasonCode: string; ruleId: string | null; copy: string };

export function DebugInfoBar({
  table,
  reasonDetails,
}: {
  table: SurfaceTable;
  reasonDetails: RiskReasonDetail[];
}) {
  const schema = table.compare?.projection_schema_digest;
  const content = table.compare?.projection_logical_digest;
  return (
    <div className="debug-info-bar" aria-label="调试信息">
      <span className="debug-info-bar__tag">Debug</span>
      <CopyDebugValue label="Raw Table" value={table.table_name} />
      {schema && <CopyDebugValue label="Schema" value={schema} />}
      {content && <CopyDebugValue label="Content" value={content} />}
      <span className="debug-info-bar__status">
        <span>表状态</span>
        <code>{table.table_status}</code>
      </span>
      {reasonDetails.map((reason) => (
        <span className="debug-info-bar__status" key={reason.reasonCode + reason.ruleId}>
          <span>风险</span>
          <code>
            {reason.reasonCode}
            {reason.ruleId ? " · " + reason.ruleId : ""}
          </code>
        </span>
      ))}
    </div>
  );
}

function CopyDebugValue({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1400);
    return () => window.clearTimeout(timer);
  }, [copied]);
  const display =
    value.startsWith("sha256:") && value.length > 19 ? value.slice(0, 19) + "…" : value;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <button
      className="debug-info-value"
      type="button"
      aria-label={`复制 ${label}`}
      title={`复制完整值：${value}`}
      onClick={() => void copy()}
    >
      <span>{label}</span>
      <code>{display}</code>
      <Copy size={12} />
      {copied && (
        <span className="sr-only" aria-live="polite">
          已复制
        </span>
      )}
    </button>
  );
}
