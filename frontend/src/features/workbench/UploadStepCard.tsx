import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, FolderOpen, RefreshCw, Upload } from "lucide-react";
import type { components } from "../api/generated/openapi";
import { gatewayApi } from "../api/application-api";
import { ApiError } from "../api/authenticated-fetch";
import { PollingConnectionLostError, createPreviewJourneyProgress, runPreviewJourney } from "../api/journeys";
import { currentGatewaySession } from "../api/session";
import { OpfsBundleStore } from "../bundle/local-bundle";
import { Button, DirectorySummary, OperationStatus, formatBytes, type OperationPhase } from "../../design-system/components";
import { operationElapsedSeconds } from "./OperationStatusPanel";
import { buildSourcePackage, collectLocalDirectory, type LocalDirectory } from "./upload-package";
import { formatWaitDuration } from "./wait-duration";

type HistoryHead = components["schemas"]["HistoryListResponse"]["head"];

export interface UploadStepCardHandle {
  chooseInitial: () => void;
  chooseModified: () => void;
  start: () => void;
}

interface DirectorySlot {
  name: string;
  directory: LocalDirectory | null;
  errors: string[];
}

const emptySlot: DirectorySlot = { name: "", directory: null, errors: [] };

type UploadPhase = "idle" | "packaging" | "uploading" | "previewing" | "downloading" | "writing" | "failed" | "done";

function errorMessage(cause: unknown, phase: UploadPhase): { message: string; code: string | null; retryable: boolean; refresh: boolean } {
  if (cause instanceof ApiError) {
    if (cause.code === "SCOPE_FORBIDDEN" || cause.status === 403) {
      return { message: "当前身份没有该操作的权限", code: "SCOPE_FORBIDDEN", retryable: false, refresh: false };
    }
    if (cause.code === "WORKSPACE_VERSION_CONFLICT" || cause.code === "BASELINE_VERSION_CONFLICT" || cause.code === "PREVIEW_BINDING_CONFLICT") {
      return { message: "工作区或基线已被更新，请刷新后重新上传", code: cause.code, retryable: false, refresh: true };
    }
    if (cause.code === "IDEMPOTENCY_CONFLICT") {
      return { message: "本次上传与服务器记录不一致，请重新开始上传", code: cause.code, retryable: true, refresh: false };
    }
    if (cause.code === "UPLOAD_STREAM_TIMEOUT" || cause.status === 408) {
      return { message: "上传超时，结果尚不确定，请重试", code: cause.code ?? "UPLOAD_STREAM_TIMEOUT", retryable: true, refresh: false };
    }
    if (cause.code === "ADMISSION_LIMIT_REACHED" || cause.status === 429) {
      return { message: "当前请求较多，请稍后重试", code: cause.code ?? "ADMISSION_LIMIT_REACHED", retryable: true, refresh: false };
    }
    if (phase === "downloading" && cause.status >= 500) {
      return { message: "预览已生成，但下载比较结果失败，请重试", code: cause.code ?? `HTTP_${cause.status}`, retryable: true, refresh: false };
    }
    return { message: cause.status >= 500 ? "服务暂时不可用，请稍后重试" : "上传或预览未完成，请重试", code: cause.code ?? `HTTP_${cause.status}`, retryable: cause.status >= 500 || cause.status === 429, refresh: false };
  }
  if (cause instanceof PollingConnectionLostError) {
    return { message: "连接中断，预览可能仍在执行。请刷新工作区查询结果。", code: "CONNECTION_LOST", retryable: true, refresh: false };
  }
  if (cause instanceof DOMException && cause.name === "TimeoutError") {
    return { message: "请求超时，请重试", code: "REQUEST_TIMEOUT", retryable: true, refresh: false };
  }
  return { message: "上传或预览未完成，请重试", code: null, retryable: true, refresh: false };
}

function slotFrom(input: FileList | File[] | null): DirectorySlot | null {
  if (!input || input.length === 0) return null;
  const result = collectLocalDirectory(input);
  const name = ((Array.from(input)[0] as File & { webkitRelativePath?: string }).webkitRelativePath ?? "").split("/")[0] ?? "";
  return { name, directory: result.directory, errors: result.errors };
}

function slotSummary(slot: DirectorySlot): string {
  if (!slot.directory) return slot.name ? `${slot.name}（未通过校验）` : "未选择";
  return `${slot.directory.rootName} · ${slot.directory.files.length} 个文件 · ${formatBytes(slot.directory.totalBytes)}`;
}

export const UploadStepCard = forwardRef<UploadStepCardHandle, {
  head: HistoryHead;
  onReloadHead: () => Promise<HistoryHead | null>;
  onUploadStateChange: (active: boolean) => void;
  onReadyChange: (ready: boolean, reason: string | null) => void;
  onComplete: (workspaceId: string, previewResultId: string) => void;
}>(function UploadStepCard({ head, onReloadHead, onUploadStateChange, onReadyChange, onComplete }, ref) {
  const initialInput = useRef<HTMLInputElement>(null);
  const modifiedInput = useRef<HTMLInputElement>(null);
  const progress = useRef(createPreviewJourneyProgress());
  const [initial, setInitial] = useState<DirectorySlot>(emptySlot);
  const [modified, setModified] = useState<DirectorySlot>(emptySlot);
  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [error, setError] = useState<{ message: string; code: string | null; retryable: boolean; refresh: boolean } | null>(null);
  const [operation, setOperation] = useState<components["schemas"]["OperationResponse"] | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [phaseDurations, setPhaseDurations] = useState<Partial<Record<UploadPhase, number>>>({});
  const phaseRef = useRef<UploadPhase>("idle");
  const phaseStartRef = useRef<number | null>(null);
  const totalStartRef = useRef<number | null>(null);

  const busy = phase === "packaging" || phase === "uploading" || phase === "previewing" || phase === "downloading" || phase === "writing";
  const ready = Boolean(modified.directory) && (!initial.name || Boolean(initial.directory));
  const blockedReason = modified.name && !modified.directory ? "本次归档组态未通过校验" : initial.name && !initial.directory ? "原始组态备份未通过校验" : modified.directory ? null : "需先选择本次归档组态目录";
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [busy]);

  useEffect(() => { onUploadStateChange(busy); }, [busy, onUploadStateChange]);
  useEffect(() => { onReadyChange(ready, blockedReason); }, [ready, blockedReason, onReadyChange]);

  function begin(next: UploadPhase) {
    const nowValue = Date.now();
    phaseRef.current = next;
    phaseStartRef.current = nowValue;
    setPhase(next);
  }

  function advance(next: UploadPhase) {
    const previous = phaseRef.current;
    const started = phaseStartRef.current;
    if (started) {
      setPhaseDurations((current) => ({ ...current, [previous]: Math.floor((Date.now() - started) / 1_000) }));
    }
    begin(next);
  }

  function clearOperationUrl() {
    try {
      const url = new URL(window.location.href);
      url.searchParams.delete("operationId");
      url.searchParams.delete("operationKind");
      window.history.replaceState(null, "", url);
    } catch { /* URL 不可用时忽略 */ }
  }

  function markFailed(cause: unknown) {
    const info = errorMessage(cause, phaseRef.current);
    setError(info);
    const started = phaseStartRef.current;
    const previous = phaseRef.current;
    if (started) {
      setPhaseDurations((current) => ({ ...current, [previous]: Math.floor((Date.now() - started) / 1_000) }));
    }
    phaseRef.current = "failed";
    phaseStartRef.current = null;
    setPhase("failed");
  }

  const selectInitial = (files: FileList | File[] | null) => {
    if (!files || files.length === 0) {
      setInitial(emptySlot);
      progress.current = createPreviewJourneyProgress();
      setError(null);
      setPhase("idle");
      setPhaseDurations({});
      return;
    }
    try {
      const next = slotFrom(files);
      if (!next) return;
      setInitial(next);
      progress.current = createPreviewJourneyProgress();
      setError(null);
      setPhase("idle");
      setPhaseDurations({});
    } catch (cause) {
      markFailed(cause);
    }
  };

  const selectModified = (files: FileList | File[] | null) => {
    if (!files || files.length === 0) {
      setModified(emptySlot);
      progress.current = createPreviewJourneyProgress();
      setError(null);
      setPhase("idle");
      setPhaseDurations({});
      return;
    }
    try {
      const next = slotFrom(files);
      if (!next) return;
      setModified(next);
      progress.current = createPreviewJourneyProgress();
      setError(null);
      setPhase("idle");
      setPhaseDurations({});
    } catch (cause) {
      markFailed(cause);
    }
  };

  async function start() {
    if (busy) return;
    if (!modified.directory) {
      setError({ message: "本次归档组态未通过校验，不能上传", code: null, retryable: false, refresh: false });
      return;
    }
    if (initial.name && !initial.directory) {
      setError({ message: "原始组态备份未通过校验，不能上传", code: null, retryable: false, refresh: false });
      return;
    }
    const session = currentGatewaySession();
    setError(null);
    setPhaseDurations({});
    setOperation(null);
    totalStartRef.current = Date.now();
    begin("packaging");
    try {
      const initialPackage = initial.directory ? await buildSourcePackage(initial.directory) : undefined;
      const modifiedPackage = await buildSourcePackage(modified.directory);
      begin("uploading");
      const result = await runPreviewJourney(gatewayApi, new OpfsBundleStore(), {
        workspaceRequest: { business_project_id: session.businessProjectId, gateway_device_external_key: session.gatewayDeviceExternalKey },
        upload: {
          inputCompleteness: initialPackage ? "FULL" : "MODIFIED_ONLY",
          initial: initialPackage ? { partName: "INITIAL", mediaType: "application/gzip", file: initialPackage } : undefined,
          modified: { partName: "MODIFIED", mediaType: "application/gzip", file: modifiedPackage },
        },
        baselineNodeId: head.node_id,
        baselineHeadVersion: head.version,
        onOperationAccepted: (operationId) => {
          try {
            sessionStorage.setItem("gateway-preview-operation", operationId);
            const url = new URL(window.location.href);
            url.searchParams.set("operationId", operationId);
            url.searchParams.set("operationKind", "operation");
            window.history.replaceState(null, "", url);
          } catch { /* URL 不可用时仍继续轮询 */ }
        },
        poll: {
          onUpdate: (value) => {
            setOperation(value);
            if (phaseRef.current === "uploading") advance("previewing");
          },
        },
        onDownloadStart: () => {
          if (phaseRef.current === "previewing") advance("downloading");
        },
        onDownloadProgress: () => {
          if (phaseRef.current === "previewing") advance("downloading");
        },
      }, progress.current);
      advance("writing");
      phaseRef.current = "done";
      setPhase("done");
      sessionStorage.removeItem("gateway-preview-operation");
      onComplete(result.workspace.workspace_id, result.preview.preview_result_id);
      progress.current = createPreviewJourneyProgress();
    } catch (cause) {
      sessionStorage.removeItem("gateway-preview-operation");
      clearOperationUrl();
      const definite = cause instanceof ApiError && cause.status >= 400 && cause.status < 500 && cause.status !== 408 && cause.status !== 429;
      if (definite) progress.current = createPreviewJourneyProgress();
      markFailed(cause);
    }
  }

  async function refreshAfterConflict() {
    setError(null);
    setPhase("idle");
    progress.current = createPreviewJourneyProgress();
    const next = await onReloadHead();
    if (!next) {
      setError({ message: "刷新失败，请检查连接后重试", code: "REFRESH_FAILED", retryable: true, refresh: false });
      phaseRef.current = "failed";
      phaseStartRef.current = null;
      setPhase("failed");
    }
  }

  useImperativeHandle(ref, () => ({
    chooseInitial: () => initialInput.current?.click(),
    chooseModified: () => modifiedInput.current?.click(),
    start: () => void start(),
  }));

  const elapsed = operation ? operationElapsedSeconds(operation, now) : null;
  const uploadStatus: OperationPhase["status"] = ["previewing", "downloading", "writing", "done"].includes(phase)
    ? "complete"
    : busy && (phase === "packaging" || phase === "uploading")
      ? "active"
      : phase === "failed" ? "failed" : "pending";
  const uploadDuration = phaseDurations.uploading !== undefined ? `${phaseDurations.uploading} 秒` : undefined;
  const modifiedOnly = !initial.directory;
  const phases: OperationPhase[] = [
    ...(initial.directory ? [{ name: "上传原始组态备份" as const, status: uploadStatus, duration: uploadDuration }] : []),
    { name: "上传本次归档组态", status: uploadStatus, duration: uploadDuration },
    ...(modifiedOnly ? [{ name: "解析预览" as const, status: phase === "previewing" ? "active" as const : ["downloading", "writing", "done"].includes(phase) ? "complete" as const : "pending" as const }] : []),
    { name: "下载预览结果", status: modifiedOnly ? (phase === "downloading" ? "active" : ["writing", "done"].includes(phase) ? "complete" : "pending") : phase === "previewing" || phase === "downloading" ? "active" : ["writing", "done"].includes(phase) ? "complete" : "pending", duration: phaseDurations.previewing !== undefined ? `${phaseDurations.previewing} 秒` : undefined },
    { name: "写入本地", status: phase === "writing" ? "active" : phase === "done" ? "complete" : "pending" },
    { name: "完成，进入差异浏览", status: phase === "done" ? "complete" : "pending" },
  ];
  return <section className="upload-card" aria-label="上传与预览" data-phase={phase}>
    <div className="upload-card__heading">
      <div><p className="eyebrow">上传</p><h3>{busy ? "上传中" : "上传组态目录"}</h3></div>
      {busy && <span className="status-tag status-tag--info">已用时 {formatWaitDuration(totalStartRef.current ? Math.floor((now - totalStartRef.current) / 1_000) : 0)}（页面计时）</span>}
    </div>
    <input ref={initialInput} type="file" className="sr-only" aria-label="选择原始组态备份目录" data-testid="upload-initial-input"
      {...{ webkitdirectory: "", directory: "" }} onChange={(event) => selectInitial(event.target.files)} />
    <input ref={modifiedInput} type="file" className="sr-only" aria-label="选择本次归档组态目录" data-testid="upload-modified-input"
      {...{ webkitdirectory: "", directory: "" }} onChange={(event) => selectModified(event.target.files)} />
    {busy ? <dl className="upload-running-summary">
      <div><dt>原始组态备份</dt><dd>{initial.directory ? initial.directory.rootName : "未选择"}</dd></div>
      <div><dt>本次归档组态</dt><dd>{modified.directory?.rootName ?? "未选择"}</dd></div>
      <div><dt>上传方式</dt><dd>{initial.directory ? "原始备份 + 本次归档" : "仅本次归档"}</dd></div>
    </dl> : <ol className="upload-steps">
      <li className="upload-step">
        <div className="upload-step__title"><span className="upload-step__index">1</span><strong>原始组态备份</strong><span className="upload-step__optional">可选</span>{initial.directory && !busy && <span className="status-tag status-tag--success">校验通过</span>}</div>
        <div className="upload-step__body">
          <Button variant="secondary" icon={<FolderOpen size={15} />} disabled={busy} disabledReason={busy ? "上传进行中" : undefined} onClick={() => initialInput.current?.click()}>选择目录</Button>
          {initial.name && <button className="link-button" onClick={() => selectInitial(null)}>清除</button>}
          {!initial.directory && <p className="upload-step__summary">{slotSummary(initial)}</p>}
          {initial.directory && !busy && <DirectorySummary directoryName={initial.directory.rootName} fileCount={initial.directory.files.length} sizeBytes={initial.directory.totalBytes} mainFile={initial.directory.mainFile} />}
          {initial.errors.length > 0 && <div className="upload-step__error" role="alert"><AlertCircle size={15} /><div><strong>原始组态备份未通过校验</strong><ul>{initial.errors.map((item) => <li key={item}>{item}</li>)}</ul><button className="link-button" onClick={() => void navigator.clipboard?.writeText(initial.errors.join("\n"))}>复制错误信息</button></div></div>}
        </div>
      </li>
      <li className="upload-step">
        <div className="upload-step__title"><span className="upload-step__index">2</span><strong>本次归档组态</strong><span className="upload-step__required">必选</span>{modified.directory && !busy && <span className="status-tag status-tag--success">校验通过</span>}</div>
        <div className="upload-step__body">
          <Button variant="secondary" icon={<FolderOpen size={15} />} disabled={busy} disabledReason={busy ? "上传进行中" : undefined} onClick={() => modifiedInput.current?.click()}>选择目录</Button>
          {modified.name && <button className="link-button" onClick={() => selectModified(null)}>清除</button>}
          {!modified.directory && <p className="upload-step__summary">{slotSummary(modified)}</p>}
          {modified.directory && !busy && <DirectorySummary directoryName={modified.directory.rootName} fileCount={modified.directory.files.length} sizeBytes={modified.directory.totalBytes} mainFile={modified.directory.mainFile} />}
          {modified.errors.length > 0 && <div className="upload-step__error" role="alert"><AlertCircle size={15} /><div><strong>本次归档组态未通过校验（{modified.errors.length} 项）</strong><ul>{modified.errors.map((item) => <li key={item}>{item}</li>)}</ul><button className="link-button" onClick={() => void navigator.clipboard?.writeText(modified.errors.join("\n"))}>复制错误信息</button></div></div>}
        </div>
      </li>
      <li className="upload-step">
        <div className="upload-step__title"><span className="upload-step__index">3</span><strong>上传</strong></div>
        <div className="upload-step__body">
          <Button variant="primary" icon={<Upload size={15} />} disabled={busy} disabledReason={!modified.name ? "需先选择本次归档组态目录" : !modified.directory ? "本次归档组态未通过校验" : initial.name && !initial.directory ? "原始组态备份未通过校验" : undefined} onClick={() => void start()}>上传并生成预览</Button>
          <p className="upload-step__summary">上传方式：{initial.directory ? "原始备份 + 本次归档" : "仅本次归档"}</p>
          <p className="upload-step__hint">上传完成后自动进入差异浏览。</p>
        </div>
      </li>
    </ol>}
    {!busy && <details className="upload-rules">
      <summary>目录要求</summary>
      <ul><li>只包含一个根目录</li><li>根目录下恰好一个 .pmc 文件</li><li>包含 sql/ 目录和 sql/dbcfg.sql</li><li>不超过 5000 个文件，总大小不超过 1GB</li></ul>
    </details>}
    {busy && <div className="upload-progress">
      <OperationStatus title="上传中" phases={phases} />
      {operation?.status === "MANUAL_RECOVERY_REQUIRED" && <div role="alert" className="form-error" title={`操作 ID：${operation.operation_id}`}><span>操作需要管理员处理。</span><span>操作 ID：<code>{operation.operation_id}</code></span><span className="form-error__actions"><button className="link-button" onClick={() => void navigator.clipboard?.writeText(operation.operation_id)}>复制 ID</button></span><span>系统仍在查询状态，刷新页面后会继续跟随。</span></div>}
      {operation && operation.status !== "MANUAL_RECOVERY_REQUIRED" && <p className="upload-progress__wait">已等待 {formatWaitDuration(elapsed ?? 0)}</p>}
      <p className="upload-progress__lock">处理中不可关闭，页面其余操作已锁定。完成后自动进入差异浏览；失败时在此显示失败步骤，可直接重试。</p>
    </div>}
    {phase === "failed" && error && <div className="upload-error" role="alert">
      <AlertCircle size={17} />
      <div><strong>{error.message}</strong>{error.code && <p>错误代码：<code>{error.code}</code></p>}
        <div className="button-row">{error.refresh ? <Button variant="secondary" icon={<RefreshCw size={15} />} onClick={() => void refreshAfterConflict()}>刷新</Button> : <Button variant="secondary" icon={<RefreshCw size={15} />} onClick={() => void start()}>重试</Button>}{error.code === "SCOPE_FORBIDDEN" && <span className="upload-error__hint">切换身份后重试，或联系管理员授予权限。</span>}</div>
      </div>
    </div>}
    {phase === "done" && <p className="upload-done" role="status"><CheckCircle2 size={16} />已完成，正在进入差异浏览…</p>}
  </section>;
});
