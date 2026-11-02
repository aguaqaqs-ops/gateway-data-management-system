import { useState } from "react";
import { Archive, Check, FolderOpen, ShieldAlert } from "lucide-react";
import { Button, ChangeBadge, Dialog, DirectorySummary, ErrorState, InfoNote, LoadingSkeleton, OperationStatus, RiskBadge } from "../design-system/components";

export function DesignSystemPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonTouched, setReasonTouched] = useState(false);
  return (
    <main className="fe1-shell" aria-labelledby="workspace-title">
      <header className="app-header">
        <div className="app-brand"><span className="app-brand__mark"><Archive size={18} /></span><div><h1 id="workspace-title">网关数据工作台</h1><span>FE1 组件与数据流能力预览</span></div></div>
        <div className="connection-status"><span className="connection-status__dot" />模拟接口 · 已连接</div>
      </header>

      <section className="page-intro">
        <div><p className="eyebrow">FRONTEND VNext · FOUNDATION</p><h2>比较工作台基础组件</h2><p>统一 token、操作层级、语义色与状态反馈，供后续工作流页面复用。</p></div>
        <Button variant="primary" icon={<FolderOpen size={16} />}>打开本地 bundle</Button>
      </section>

      <div className="component-grid">
        <section className="showcase-card showcase-card--wide">
          <div className="card-heading"><div><span className="section-kicker">P1 · BUTTONS</span><h3>操作层级</h3></div><span className="subtle-label">每个操作区至多一个主要按钮</span></div>
          <div className="button-row button-row--wrap">
            <Button variant="primary" icon={<Check size={15} />}>主要操作</Button>
            <Button variant="secondary">次要操作</Button>
            <Button variant="ghost">幽灵操作</Button>
            <Button variant="danger" icon={<ShieldAlert size={15} />}>危险操作</Button>
            <Button variant="secondary" disabledReason="请先完成上传校验">不可用操作</Button>
          </div>
        </section>

        <section className="showcase-card">
          <div className="card-heading"><div><span className="section-kicker">P1 · SEMANTIC COLOR</span><h3>差异与风险分开表达</h3></div></div>
          <div className="badge-stack"><div><ChangeBadge kind="ADDED" /><ChangeBadge kind="DELETED" /><ChangeBadge kind="UPDATED" /><ChangeBadge kind="UNCHANGED" /></div><div><RiskBadge level="HIGH" /><RiskBadge level="MEDIUM_HIGH" /><RiskBadge level="MEDIUM_LOW" /><RiskBadge level="LOW" /><RiskBadge level="UNKNOWN" /></div></div>
          <InfoNote>差异徽章说明变化类型；风险颜色只表示 RiskReport 的评估结果。</InfoNote>
        </section>

        <section className="showcase-card">
          <div className="card-heading"><div><span className="section-kicker">P2 · SELECTED INPUT</span><h3>已选目录与校验</h3></div></div>
          <DirectorySummary directoryName="站点A_2026-11-02" fileCount={18} sizeBytes={2_764_800} mainFile="config/main.xml" validationErrors={["缺少可选说明文件 README.txt"]} />
          <p className="selection-retained">校验提示以内联方式呈现，目录选择保留。</p>
        </section>

        <section className="showcase-card">
          <div className="card-heading"><div><span className="section-kicker">P2 · OPERATION</span><h3>操作进度</h3></div><span className="subtle-label">阶段耗时 · 可重试失败阶段</span></div>
          <OperationStatus title="正在生成比较结果" phases={[
            { name: "接收上传", status: "complete", duration: "2.4 秒" },
            { name: "读取组态表", status: "complete", duration: "8.1 秒" },
            { name: "生成差异与风险", status: "failed", duration: "超时" },
          ]} onRetry={() => undefined} />
        </section>

        <section className="showcase-card">
          <div className="card-heading"><div><span className="section-kicker">P2 · LOADING</span><h3>内容骨架</h3></div></div>
          <LoadingSkeleton />
        </section>

        <section className="showcase-card">
          <div className="card-heading"><div><span className="section-kicker">P2 · ERROR</span><h3>错误恢复</h3></div></div>
          <ErrorState code="BUNDLE_INTEGRITY_MISMATCH" details="产物摘要校验未通过。已丢弃本地副本，可重新下载。" onRetry={() => undefined} />
        </section>

        <section className="showcase-card showcase-card--wide showcase-card--dialog">
          <div className="card-heading"><div><span className="section-kicker">P2 · CONFIRMATION</span><h3>应用内对话框</h3></div><span className="subtle-label">不用浏览器原生弹窗</span></div>
          <div className="dialog-example"><p>破坏性操作显示影响摘要；需要理由时在对话框内完成必填校验。</p><Button variant="danger" onClick={() => { setReason(""); setReasonTouched(false); setDialogOpen(true); }}>预览退回确认</Button></div>
        </section>
      </div>

      <footer className="page-footer"><span>表格主题与页面共用字体和 token</span><span>本地 bundle · 按表懒解析 · 浏览期间不请求后端</span></footer>
      <Dialog open={dialogOpen} title="退回这次提交？" description="退回操作会结束当前审核流程，并记录操作人和时间。" onClose={() => setDialogOpen(false)} actions={<><Button variant="secondary" onClick={() => setDialogOpen(false)}>取消</Button><Button variant="danger" disabledReason={!reason.trim() ? "填写理由后才能确认" : undefined} onClick={() => setDialogOpen(false)}>确认退回</Button></>}>
        <label className="field-label" htmlFor="review-reason">退回理由 <span>必填</span></label>
        <textarea id="review-reason" className="text-area" rows={3} placeholder="填写理由" required value={reason} onChange={(event) => setReason(event.currentTarget.value)} onBlur={() => setReasonTouched(true)} aria-invalid={reasonTouched && !reason.trim()} />
        {reasonTouched && !reason.trim() && <p className="field-error">请填写退回理由。</p>}
        <p className="field-hint">实际业务操作由页面命令调用；此弹窗只展示可复用的确认样式。</p>
      </Dialog>
    </main>
  );
}
