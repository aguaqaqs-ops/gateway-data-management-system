import { describe, expect, it } from "vitest";
import {
  baselineDisplayName,
  describeSubmitSummary,
  submissionDisplayName,
} from "./submit-summary";
import { HISTORY_PAGE_ONE, HISTORY_PAGE_TWO } from "../dev/mock-data";

const history = {
  ...HISTORY_PAGE_ONE,
  nodes: [...HISTORY_PAGE_ONE.nodes, ...HISTORY_PAGE_TWO.nodes],
  next_cursor: null,
};

describe("submit summary display names (M7)", () => {
  it("resolves the head baseline with its kind label", () => {
    expect(baselineDisplayName(history, "fe2a-history-ref-1")).toBe(
      "当前基线（归档基线 1）",
    );
  });

  it("resolves a submission by creation order", () => {
    expect(
      submissionDisplayName(history, "submission", "fe2a-history-ref-2"),
    ).toBe("提交 2");
    expect(
      submissionDisplayName(history, "submission", "fe2a-history-ref-old"),
    ).toBe("提交 1");
  });

  it("describes the dialog summary with display names", () => {
    const rows = describeSubmitSummary(
      {
        workspace_id: "workspace-fe2b",
        preview_result_id: "preview-full",
        business_baseline_node_id: "fe2a-history-ref-1",
        generation: 3,
      },
      history,
      "gateway-17",
    );
    expect(rows).toEqual([
      { term: "工作区", display: "gateway-17", raw: "workspace-fe2b" },
      { term: "Preview", display: "本次预览", raw: "preview-full" },
      {
        term: "业务基线",
        display: "当前基线（归档基线 1）",
        raw: "fe2a-history-ref-1",
      },
      { term: "代次", display: "3", raw: 3 },
    ]);
  });

  it("falls back to raw IDs when history has no matching node", () => {
    const rows = describeSubmitSummary(
      {
        workspace_id: "workspace-fe2b",
        preview_result_id: "preview-unknown",
        business_baseline_node_id: "missing-baseline",
        generation: 3,
      },
      { head: history.head, nodes: [] },
    );
    expect(rows[1]).toMatchObject({
      term: "Preview",
      display: "本次预览",
      raw: "preview-unknown",
    });
    expect(rows[2]).toMatchObject({
      term: "业务基线",
      display: "missing-baseline",
      raw: "missing-baseline",
    });
  });

  it("falls back to the raw workspace ID when no display name is available", () => {
    const rows = describeSubmitSummary(
      {
        workspace_id: "workspace-fe2b",
        preview_result_id: "preview-full",
        business_baseline_node_id: "fe2a-history-ref-1",
        generation: 3,
      },
      history,
      null,
    );
    expect(rows[0]).toEqual({ term: "工作区", display: "workspace-fe2b", raw: "workspace-fe2b" });
  });

  it("falls back to raw baseline ID when history is unavailable", () => {
    const rows = describeSubmitSummary(
      {
        workspace_id: "workspace-fe2b",
        preview_result_id: "preview-full",
        business_baseline_node_id: "fe2a-history-ref-1",
        generation: 3,
      },
      null,
    );
    expect(rows[2]).toMatchObject({
      display: "fe2a-history-ref-1",
      raw: "fe2a-history-ref-1",
    });
  });
});
