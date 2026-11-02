export function WorkspacePage() {
  return (
    <main className="workspace-shell" aria-labelledby="workspace-title">
      <header className="workspace-shell__header">
        <h1 id="workspace-title">网关数据工作台</h1>
        <span className="connection-status">
          <span className="connection-status__dot" aria-hidden="true" />
          工程骨架
        </span>
      </header>
      <section className="workspace-shell__body" aria-label="工作区">
        <p>FE0 工程结构已就绪，业务工作流将在后续阶段接入。</p>
      </section>
    </main>
  );
}
