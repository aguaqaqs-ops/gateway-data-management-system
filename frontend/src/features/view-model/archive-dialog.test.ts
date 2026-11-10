import { describe, expect, it } from "vitest";
import type { components } from "../api/generated/openapi";
import {
  anomalyAction,
  anomalyDetailText,
  blockerCopy,
  closeError,
  formatReasonLimitError,
  generatedTimeStatusText,
  ISSUE_COPY,
  resolutionError,
  resolutionStatusCopy,
  resolutionStatusTone,
  startDisabledReason,
  statusTagClass,
  utf8Length,
} from "./archive-dialog";

type Schemas = components["schemas"];
type Anomaly = Schemas["ArchivePreviewAnomalyResponse"];

function anomaly(overrides: { issue_code: string; subject_kind: Anomaly["subject_kind"]; [key: string]: unknown }): Anomaly {
  return {
    target_submission_id: "v-s1",
    target_candidate_digest: "sha256:v-candidate-v-s1",
    subject_digest: "sha256:v-anomaly",
    accepted_at: null,
    accepted_by: null,
    affected_submission_ids: ["v-s1"],
    details: {},
    detected_status: "DETECTED",
    latest_sequence: 0,
    reason: null,
    relations: [],
    resolution_status: "UNRESOLVED",
    side: "MODIFIED",
    ...overrides,
  } as unknown as Anomaly;
}

describe("archive dialog view copy", () => {
  it("uses the kickoff wording for baseline time and generated-time details", () => {
    expect(ISSUE_COPY.BASELINE_TIME_UNAVAILABLE).toBe("当前基线没有可用的生成时间，本轮无法比较时间先后");
    expect(generatedTimeStatusText({ status: "COLUMN_ABSENT" })).toBe("version_manager 表没有 saved_time 列");
    expect(generatedTimeStatusText({ status: "NO_VALUE", empty_count: 12 })).toBe("saved_time 全部为空（12 行）");
    expect(generatedTimeStatusText({ status: "NO_VALID_VALUE", invalid_count: 3 })).toBe("saved_time 没有可识别的时间（3 个无法识别）");
  });

  it("renders BASELINE_TIME_UNAVAILABLE details with the shared generated-time counts", () => {
    const baseline = anomaly({
      issue_code: "BASELINE_TIME_UNAVAILABLE",
      subject_kind: "CONFIGURATION_TIME_QUALITY",
      side: "BASELINE",
      details: { generated_time: { status: "NO_VALUE", empty_count: 9 } },
    });
    expect(anomalyDetailText(baseline, (id) => id)).toBe("saved_time 全部为空（9 行）；比较结果：无法比较");
    const missing = anomaly({
      issue_code: "GENERATION_TIME_MISSING",
      subject_kind: "CONFIGURATION_TIME_QUALITY",
      details: { generated_time: { status: "NO_VALID_VALUE", invalid_count: 4 } },
    });
    expect(anomalyDetailText(missing, (id) => id)).toBe("saved_time 没有可识别的时间（4 个无法识别）");
  });

  it("covers the four §16.3 detail mappings missing from C10", () => {
    const unexplained = anomaly({
      issue_code: "INITIAL_SOURCE_UNEXPLAINED",
      subject_kind: "CONFIGURATION_SOURCE",
      details: {
        edges: [{ submission_id: "v-s1", initial: { canonical_state_digest: "aaaabbbbccccdddd" }, modified: { canonical_state_digest: "1111222233334444" } }],
        states: [{ canonical_state_digest: "aaaabbbbccccdddd" }, { canonical_state_digest: "5555666677778888" }],
      },
    });
    expect(anomalyDetailText(unexplained, (id) => `名(${id})`)).toBe(
      "与当前基线及本轮已通过的提交都对不上，可能漏传了现场的改动。候选：名(v-s1)的①/②（aaaabbbbcccc…/111122223333…）；状态数 2。",
    );
    const lastNotMax = anomaly({
      issue_code: "GENERATION_TIME_LAST_NOT_MAX",
      subject_kind: "CONFIGURATION_TIME_QUALITY",
      details: {
        generated_time: {
          selected_time_utc: "2026-11-06T12:00:00Z",
          last_valid_source_row: 7,
          max_valid_time_utc: "2026-11-07T12:00:00Z",
          max_valid_source_row: 3,
        },
      },
    });
    expect(anomalyDetailText(lastNotMax, (id) => id)).toBe(
      "采用最后一个有效值 2026-11-06T12:00:00Z（第 7 行），最大值为 2026-11-07T12:00:00Z（第 3 行）。不会自动改用最大值。",
    );
    const initialBeforeBaseline = anomaly({
      issue_code: "TIME_ABNORMAL_INITIAL",
      subject_kind: "CONFIGURATION_TIME_ORDER",
      details: { comparisons: [{ relation: "INITIAL_BEFORE_BASELINE", left_time_utc: "2026-11-06T12:00:00Z", right_time_utc: "2026-11-07T12:00:00Z" }] },
    });
    expect(anomalyDetailText(initialBeforeBaseline, (id) => id)).toBe("① 2026-11-06 12:00:00 UTC 早于当前基线 2026-11-07 12:00:00 UTC");
    const modifiedBeforeInitial = anomaly({
      issue_code: "TIME_ABNORMAL_MODIFIED",
      subject_kind: "CONFIGURATION_TIME_ORDER",
      details: { comparisons: [{ relation: "MODIFIED_BEFORE_INITIAL", left_time_utc: "2026-11-06T12:00:00Z", right_time_utc: "2026-11-05T12:00:00Z" }] },
    });
    expect(anomalyDetailText(modifiedBeforeInitial, (id) => id)).toBe("② 2026-11-06 12:00:00 UTC 早于 ① 2026-11-05 12:00:00 UTC");
  });

  it("maps TIME_ABNORMAL and sibling details to §16.3 text", () => {
    const regressed = anomaly({
      issue_code: "TIME_ABNORMAL_MODIFIED",
      subject_kind: "CONFIGURATION_TIME_ORDER",
      details: { comparisons: [{ relation: "MODIFIED_BEFORE_BASELINE", left_time_utc: "2026-11-06T12:00:00Z", right_time_utc: "2026-11-07T12:00:00Z" }] },
    });
    expect(anomalyDetailText(regressed, (id) => `名(${id})`)).toBe("② 2026-11-06 12:00:00 UTC 早于当前基线 2026-11-07 12:00:00 UTC");
    const sibling = anomaly({
      issue_code: "APPROVED_SIBLING_EXCLUDED",
      subject_kind: "APPROVED_SIBLING_EXCLUDED",
      target_submission_id: "v-s2",
      side: null,
    });
    expect(anomalyDetailText(sibling, (id) => `名(${id})`)).toBe("目标提交名(v-s2)");
  });
});

describe("archive dialog status labels", () => {
  it("keeps ACCEPTED neutral and never the success tone", () => {
    expect(resolutionStatusCopy("ACCEPTED")).toBe("已接受");
    expect(resolutionStatusTone("ACCEPTED")).toBe("neutral");
    const className = statusTagClass(resolutionStatusTone("ACCEPTED"));
    expect(className).not.toContain("success");
    expect(className).toBe("status-tag status-tag--neutral");
  });

  it("marks REVOKED and UNRESOLVED as warning with the kickoff wording", () => {
    expect(resolutionStatusCopy("REVOKED")).toBe("已撤销接受，需要重新处理");
    expect(resolutionStatusCopy("UNRESOLVED")).toBe("未处理");
    expect(statusTagClass(resolutionStatusTone("REVOKED"))).toBe("status-tag status-tag--warning");
  });
});

describe("archive dialog action mapping", () => {
  it.each([
    ["APPROVED_SIBLING_EXCLUDED", "ACKNOWLEDGE_EXCLUSION"],
    ["PROJECT_IDENTITY_EXCEPTION", "ACKNOWLEDGE_IDENTITY_EXCEPTION"],
    ["CONFIGURATION_SOURCE", "ACKNOWLEDGE_SOURCE_EXCEPTION"],
    ["CONFIGURATION_TIME_QUALITY", "ACKNOWLEDGE_TIME_QUALITY"],
    ["CONFIGURATION_TIME_ORDER", "ACKNOWLEDGE_TIME_ORDER"],
  ] as const)("maps %s to %s", (subjectKind, action) => {
    expect(anomalyAction(anomaly({ issue_code: "GENERATION_TIME_MISSING", subject_kind: subjectKind }))).toBe(action);
  });
});

describe("archive dialog reason limits", () => {
  it("counts UTF-8 bytes and rejects only above 4096", () => {
    expect(utf8Length("多")).toBe(3);
    expect(formatReasonLimitError("close", "", 0)).toBe("请填写关闭理由");
    expect(formatReasonLimitError("accept", "", 0)).toBe("请填写接受理由");
    expect(formatReasonLimitError("revoke", "", 0)).toBe("请填写撤销理由");
    const atLimit = "多".repeat(1365) + "x";
    expect(utf8Length(atLimit)).toBe(4096);
    expect(formatReasonLimitError("close", atLimit, utf8Length(atLimit))).toBeUndefined();
    const overLimit = `${atLimit}x`;
    expect(utf8Length(overLimit)).toBe(4097);
    expect(formatReasonLimitError("close", overLimit, utf8Length(overLimit))).toBe("理由不能超过 4096 字节");
  });
});

describe("archive start disabled reason", () => {
  const base = {
    loading: false,
    loadError: null,
    plan: {},
    blockerCount: 0,
    unknownCount: 0,
    unprocessedCount: 0,
    confirmSelection: true,
    running: false,
  };

  it("puts the precheck state first", () => {
    expect(startDisabledReason({ ...base, loading: true, blockerCount: 1 })).toBe("正在预检");
    expect(startDisabledReason({ ...base, loadError: { code: "HTTP_500" }, blockerCount: 1 })).toBe("预检失败，请先处理错误");
    expect(startDisabledReason({ ...base, plan: null })).toBe("预检失败，请先处理错误");
    expect(startDisabledReason({ ...base, loadError: { code: "SCOPE_FORBIDDEN" } })).toBe("当前身份没有归档权限");
  });

  it("follows blocker, unknown, unprocessed, checkbox and running order", () => {
    expect(startDisabledReason({ ...base, blockerCount: 1, unknownCount: 1, unprocessedCount: 1 })).toBe("当前预检存在阻断项");
    expect(startDisabledReason({ ...base, unknownCount: 1, unprocessedCount: 1 })).toBe("存在当前版本不能处理的项");
    expect(startDisabledReason({ ...base, unprocessedCount: 2 })).toBe("还有 2 项异常未处理");
    expect(startDisabledReason({ ...base, confirmSelection: false })).toBe("请确认归档选择");
    expect(startDisabledReason({ ...base, running: true })).toBe("归档中…");
    expect(startDisabledReason(base)).toBeUndefined();
  });
});

describe("archive dialog error copy", () => {
  it("maps blockers to the kickoff table", () => {
    expect(blockerCopy("ARCHIVE_PENDING_REVIEW")).toEqual({ text: "待审核的提交", pendingReview: true });
    expect(blockerCopy("ACTIVE_SUBMIT_ATTEMPT").text).toBe("已有提交正在处理，完成后才能归档");
    expect(blockerCopy("ARCHIVE_INTEGRITY_FAILURE").text).toBe("归档数据完整性校验未通过，不能继续，请联系管理员");
    expect(blockerCopy("FUTURE_BLOCKER").text).toBe("当前不能归档");
  });

  it("never shows the server message for close 404/413 and other codes", () => {
    expect(closeError({ status: 404, code: "RESOURCE_NOT_FOUND", message: "raw server text" })).toEqual({ title: "未找到该提交，请重新预检", code: "RESOURCE_NOT_FOUND" });
    expect(closeError({ status: 413, code: "PAYLOAD_TOO_LARGE", message: "raw server text" })).toEqual({ title: "关闭未完成", code: "PAYLOAD_TOO_LARGE" });
    expect(closeError({ status: 503, code: "UNAVAILABLE", message: "raw server text" })).toEqual({ title: "关闭未完成", code: "UNAVAILABLE" });
    expect(closeError({ status: 409, code: "ARCHIVE_CLOSED" })).toEqual({ title: "该提交已归档或关闭", code: "ARCHIVE_CLOSED" });
  });

  it("never shows the server message for accept/revoke failures", () => {
    expect(resolutionError({ status: 429, code: "RATE_LIMITED", message: "raw server text" })).toEqual({ title: "操作未完成", code: "RATE_LIMITED" });
    expect(resolutionError({ status: 422, code: "REQUEST_VALIDATION_FAILED", message: "raw server text" })).toEqual({ title: "理由或请求不符合要求", code: "REQUEST_VALIDATION_FAILED" });
  });
});
