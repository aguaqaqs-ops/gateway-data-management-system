import {
  alignFormulaLines,
  renderFormulaLines,
  type AlignedFormulaLine,
  type FormulaLine,
} from "../../features/view-model/formula-view";
import type { FormulaDisplay } from "../../features/view-model/model";

export function FormulaCard({ formula, preview }: { formula: FormulaDisplay; preview: boolean }) {
  const title =
    formula.deleted && preview ? "删除记录中的基线公式" : preview ? "上传侧公式" : "改后公式";
  const currentDevices =
    formula.deleted && preview ? formula.beforeDevices : formula.currentDevices;
  const singleFormula = formula.currentFormula;
  const lines = renderFormulaLines(singleFormula, currentDevices);
  const beforeLines = renderFormulaLines(formula.beforeFormula, formula.beforeDevices);
  const currentLines = renderFormulaLines(formula.currentFormula, formula.currentDevices);
  const aligned = alignFormulaLines(beforeLines, currentLines);
  return (
    <section className="formula-card">
      <div className="formula-card__heading">
        <strong>
          {formula.currentDeviceName ?? formula.beforeDeviceName ?? "未知装置"}
          {" · "}
          {formula.pointLabel}
        </strong>
        {(formula.label || (formula.changed && !preview)) && (
          <span className="formula-changed">公式已改</span>
        )}
      </div>
      {preview && !formula.beforeFormula ? (
        <section className="formula-side formula-side--single">
          <strong>{title}</strong>
          <FormulaLineList lines={lines} />
        </section>
      ) : (
        <div className="formula-pair">
          <strong className="formula-pair__heading">改前公式</strong>
          <strong className="formula-pair__heading">改后公式</strong>
          {aligned.length ? (
            aligned.map((line, index) => (
              <FormulaAlignedPair
                key={line.before?.key ?? line.current?.key ?? index}
                line={line}
              />
            ))
          ) : (
            <div className="formula-empty formula-empty--span">暂无公式</div>
          )}
        </div>
      )}
    </section>
  );
}

function FormulaAlignedPair({ line }: { line: AlignedFormulaLine }) {
  const state = line.state === "same" ? "" : ` formula-line--${line.state}`;
  const beforeKind = line.before?.kind === "group" ? " formula-line--group" : "";
  const currentKind = line.current?.kind === "group" ? " formula-line--group" : "";
  return (
    <>
      <div
        className={`formula-line${beforeKind}${state}`}
        style={{ paddingLeft: 7 + (line.before?.depth ?? 0) * 14 }}
      >
        {line.before?.text ?? " "}
      </div>
      <div
        className={`formula-line${currentKind}${state}`}
        style={{ paddingLeft: 7 + (line.current?.depth ?? 0) * 14 }}
      >
        {line.current?.text ?? " "}
      </div>
    </>
  );
}

function FormulaLineList({ lines }: { lines: FormulaLine[] }) {
  if (!lines.length) return <div className="formula-empty">暂无公式</div>;
  return (
    <div className="formula-lines">
      {lines.map((line) => (
        <div
          key={line.key}
          className={line.kind === "group" ? "formula-line formula-line--group" : "formula-line"}
          style={{ paddingLeft: 7 + line.depth * 14 }}
        >
          {line.text}
        </div>
      ))}
    </div>
  );
}
