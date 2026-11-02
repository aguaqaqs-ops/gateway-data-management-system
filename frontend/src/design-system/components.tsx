import { useEffect, useId, useRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { AlertCircle, CheckCircle2, Copy, Info, LoaderCircle, X } from "lucide-react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  icon?: ReactNode;
  disabledReason?: string;
}

export function Button({ variant = "secondary", icon, disabledReason, children, className = "", disabled, id, "aria-describedby": describedBy, ...props }: ButtonProps) {
  const isDisabled = disabled || Boolean(disabledReason);
  const generatedId = useId();
  const reasonId = `${id ?? `button-${generatedId}`}-disabled-reason`;
  return (
    <span className="button-wrap">
      <button id={id} className={`button button--${variant} ${className}`} disabled={isDisabled} aria-describedby={disabledReason ? reasonId : describedBy} {...props}>
        {icon}<span>{children}</span>
      </button>
      {disabledReason && <span className="disabled-reason" id={reasonId}>{disabledReason}</span>}
    </span>
  );
}

export function RiskBadge({ level }: { level: "HIGH" | "MEDIUM_HIGH" | "MEDIUM_LOW" | "LOW" | "UNKNOWN" }) {
  const labels = { HIGH: "高风险", MEDIUM_HIGH: "中高风险", MEDIUM_LOW: "中低风险", LOW: "低风险", UNKNOWN: "未知风险" };
  return <span className={`risk-badge risk-${level.toLowerCase().replace("_", "-")}`} aria-label={labels[level]}>{labels[level]}</span>;
}

export function ChangeBadge({ kind }: { kind: "ADDED" | "DELETED" | "UPDATED" | "UNCHANGED" }) {
  const labels = { ADDED: "新增", DELETED: "删除", UPDATED: "更新", UNCHANGED: "未变更" };
  const symbols = { ADDED: "+", DELETED: "−", UPDATED: "↔", UNCHANGED: "=" };
  return <span className={`change-badge diff-${kind.toLowerCase()}`} aria-label={labels[kind]}><span aria-hidden="true">{symbols[kind]}</span><span className="change-badge__label">{labels[kind]}</span></span>;
}

export interface DialogProps {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  actions?: ReactNode;
}

export function Dialog({ open, title, description, onClose, children, actions }: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const priorFocus = useRef<HTMLElement | null>(null);
  const closeHandler = useRef(onClose);
  const id = useId();

  useEffect(() => { closeHandler.current = onClose; }, [onClose]);

  useEffect(() => {
    if (!open) return;
    priorFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    const first = dialog?.querySelector<HTMLElement>("button:not([disabled]), input:not([disabled]), [tabindex='0']");
    first?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); closeHandler.current(); }
      if (event.key !== "Tab" || !dialog) return;
      const focusable = [...dialog.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex='0']")];
      if (!focusable.length) return;
      const firstItem = focusable[0];
      const lastItem = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === firstItem) { event.preventDefault(); lastItem?.focus(); }
      else if (!event.shiftKey && document.activeElement === lastItem) { event.preventDefault(); firstItem?.focus(); }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      priorFocus.current?.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby={`dialog-title-${id}`} aria-describedby={description ? `dialog-description-${id}` : undefined}>
        <header className="dialog__header">
          <div><h2 id={`dialog-title-${id}`}>{title}</h2>{description && <p id={`dialog-description-${id}`}>{description}</p>}</div>
          <button className="icon-button" aria-label="关闭对话框" onClick={onClose}><X size={18} /></button>
        </header>
        <div className="dialog__body">{children}</div>
        {actions && <footer className="dialog__actions">{actions}</footer>}
      </section>
    </div>
  );
}

export interface DirectorySummaryProps {
  directoryName: string;
  fileCount: number;
  sizeBytes: number;
  mainFile: string;
  validationErrors?: string[];
}

export function DirectorySummary({ directoryName, fileCount, sizeBytes, mainFile, validationErrors = [] }: DirectorySummaryProps) {
  return (
    <section className="directory-summary" aria-label="已选目录">
      <div className="directory-summary__heading"><strong>{directoryName}</strong><span>{fileCount} 个文件 · {formatBytes(sizeBytes)}</span></div>
      <p>主文件：<code>{mainFile}</code></p>
      {validationErrors.length > 0 && <ul className="inline-errors" aria-live="polite">{validationErrors.map((error) => <li key={error}><AlertCircle size={14} />{error}</li>)}</ul>}
    </section>
  );
}

export interface OperationPhase {
  name: string;
  duration?: string;
  status: "pending" | "active" | "complete" | "failed";
}

export function OperationStatus({ title, phases, onRetry }: { title: string; phases: OperationPhase[]; onRetry?: () => void }) {
  const failed = phases.find((phase) => phase.status === "failed");
  return (
    <section className="operation-card" aria-live="polite" aria-label="操作状态">
      <div className="operation-card__title"><LoaderCircle className={phases.some((phase) => phase.status === "active") ? "spin" : ""} size={18} /><strong>{title}</strong></div>
      <ol className="operation-timeline">{phases.map((phase) => <li className={`operation-phase operation-phase--${phase.status}`} key={phase.name}>
        <span className="operation-phase__marker">{phase.status === "complete" ? <CheckCircle2 size={16} /> : phase.status === "failed" ? <AlertCircle size={16} /> : null}</span>
        <span>{phase.name}</span><small>{phase.duration ?? (phase.status === "active" ? "进行中" : "")}</small>
      </li>)}</ol>
      {failed && onRetry && <Button variant="secondary" icon={<LoaderCircle size={15} />} onClick={onRetry}>重试失败阶段</Button>}
    </section>
  );
}

export function LoadingSkeleton({ label = "正在加载比较结果" }: { label?: string }) {
  return <section className="loading-skeleton" aria-label={label} aria-busy="true">
    <div className="skeleton-line skeleton-line--wide" /><div className="skeleton-line skeleton-line--medium" />
    <div className="skeleton-layout"><div className="skeleton-block" /><div className="skeleton-block skeleton-block--large" /></div>
    <span className="sr-only">{label}</span>
  </section>;
}

export function ErrorState({ code, details, onRetry }: { code: string; details: string; onRetry: () => void }) {
  const copyDetails = async () => navigator.clipboard?.writeText(`${code}\n${details}`);
  return <section className="error-state" role="alert">
    <div className="error-state__icon"><AlertCircle size={22} /></div>
    <div className="error-state__content"><h3>暂时无法显示结果</h3><p>错误代码：<code>{code}</code></p>
      <details><summary>错误详情</summary><pre>{details}</pre></details>
      <div className="button-row"><Button variant="primary" onClick={onRetry}>重试</Button><Button variant="ghost" icon={<Copy size={15} />} onClick={() => void copyDetails()}>复制详情</Button></div>
    </div>
  </section>;
}

export function InfoNote({ children }: { children: ReactNode }) {
  return <div className="info-note"><Info size={16} aria-hidden="true" /><span>{children}</span></div>;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let size = bytes / 1024;
  for (const unit of units) {
    if (size < 1024 || unit === "GB") return `${size.toFixed(size >= 10 ? 0 : 1)} ${unit}`;
    size /= 1024;
  }
  return `${size.toFixed(1)} GB`;
}
