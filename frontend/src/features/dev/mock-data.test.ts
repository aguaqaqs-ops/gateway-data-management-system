import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  ARCHIVE_PLAN_NEEDS_CONFIRMATION, HISTORY_PAGE_ONE, HISTORY_PAGE_TWO, HISTORY_COMPARE_STATUS_SCENARIOS, MANUAL_RECOVERY_TO_FAILED,
  MANUAL_RECOVERY_TO_SUCCESS, SIMULATED_ERROR_RESPONSES, SIMULATED_STRING_VALUES, TEST_ARCHIVE_ANOMALY_EVENT, TEST_ARCHIVE_CONFIRM_EVENT,
  ARCHIVE_PLAN_READY, COMPLETE_RESPONSE_SCENARIOS, OPERATION_TERMINAL_RESPONSES, TEST_ARCHIVE_CANDIDATES, TEST_ARCHIVE_CANDIDATES_BLOCKED,
  TEST_HISTORY_CURSOR_FIRST, TEST_HISTORY_CURSOR_SECOND, TEST_OPERATION_RUNNING, TEST_OPERATION_SUCCEEDED, TEST_SUBMIT_ACCEPTED, TEST_UPLOAD_FULL, TEST_WORKSPACE, WRITE_SCENARIO_COVERAGE, validateSimulatedRequest,
} from "./simulated-api";
import { OPERATION_STATUS_COPY } from "../view-model/operation-status-copy";
import { WORKSPACE_STATE_COPY } from "../view-model/workspace-state-copy";

describe("simulated HTTP response contracts", () => {
  it("uses only error codes documented for each route and status", async () => {
    const openapi = JSON.parse(await readFile(resolve(process.cwd(), "openapi.json"), "utf8")) as {
      paths: Record<string, Record<string, { responses?: Record<string, { description?: string }> }>>;
    };
    for (const scenario of SIMULATED_ERROR_RESPONSES) {
      const response = openapi.paths[scenario.route]?.[scenario.method.toLowerCase()]?.responses?.[String(scenario.status)];
      expect(response, `${scenario.method} ${scenario.route} ${scenario.status}`).toBeDefined();
      expect(scenario.schema).toBe("ErrorResponse");
      expect(Object.keys(scenario.body).sort()).toEqual(["code", "message"]);
      const documentedCodes = (response?.description ?? "").split(/,|\bor\b/).map((code) => code.trim()).filter(Boolean);
      expect(documentedCodes, `${scenario.method} ${scenario.route} ${scenario.status} ${scenario.body.code}`).toContain(scenario.body.code);
    }
  });

  it("covers every public v1 write route and its success, permission, version, and idempotency outcomes", async () => {
    const openapi = JSON.parse(await readFile(resolve(process.cwd(), "openapi.json"), "utf8")) as {
      paths: Record<string, Record<string, { responses?: Record<string, { description?: string }> }>>;
    };
    const writes = Object.entries(openapi.paths).filter(([route, methods]) => route.startsWith("/v1/") && methods.post).map(([route]) => route).sort();
    expect(WRITE_SCENARIO_COVERAGE.map((scenario) => scenario.route).sort()).toEqual(writes);
    for (const scenario of WRITE_SCENARIO_COVERAGE) {
      const operation = openapi.paths[scenario.route]?.post;
      expect(operation).toBeDefined();
      const outcomes = scenario.outcomes.join(" ");
      expect(outcomes).toMatch(/success:/);
      expect(outcomes).toContain("403:SCOPE_FORBIDDEN");
      const conflictDescriptions = Object.entries(operation?.responses ?? {}).filter(([status]) => status === "409").map(([, response]) => response.description ?? "");
      const declaredConflicts = conflictDescriptions.flatMap((description) => description.split(/,|\bor\b/).map((code) => code.trim())).filter((code) => code === "IDEMPOTENCY_CONFLICT" || code.endsWith("VERSION_CONFLICT"));
      for (const code of declaredConflicts) expect(outcomes).toContain(code);
      for (const outcome of scenario.outcomes) {
        const success = /^(?:success|replay):(\d+)$/.exec(outcome);
        if (success) {
          expect(COMPLETE_RESPONSE_SCENARIOS.some((entry) => entry.method === "POST" && entry.route === scenario.route && entry.status === Number(success[1]))).toBe(true);
          continue;
        }
        const error = /^(\d+):(.+)$/.exec(outcome);
        if (error) expect(SIMULATED_ERROR_RESPONSES.some((entry) => entry.method === "POST" && entry.route === scenario.route && entry.status === Number(error[1]) && entry.body.code === error[2])).toBe(true);
      }
    }
  });

  it("uses OpenAPI success statuses, with only the documented backend timing exceptions", async () => {
    const openapi = JSON.parse(await readFile(resolve(process.cwd(), "openapi.json"), "utf8")) as {
      paths: Record<string, Record<string, { responses?: Record<string, unknown> }>>;
    };
    for (const scenario of COMPLETE_RESPONSE_SCENARIOS) {
      const route = scenario.route.split("?")[0] ?? scenario.route;
      const declared = openapi.paths[route]?.[scenario.method.toLowerCase()]?.responses?.[String(scenario.status)];
      const backendTimingException = (scenario.status === 201 && route === "/v1/workspaces")
        || (scenario.status === 202 && route === "/v1/history-compares");
      expect(declared !== undefined || backendTimingException, `${scenario.method} ${route} ${scenario.status}`).toBe(true);
    }
  });

  it("keeps OpenAPI string fields within backend source values", () => {
    const operationValues = [TEST_OPERATION_RUNNING, TEST_OPERATION_SUCCEEDED, ...Object.values(OPERATION_TERMINAL_RESPONSES), ...MANUAL_RECOVERY_TO_SUCCESS, ...MANUAL_RECOVERY_TO_FAILED];
    for (const operation of operationValues) {
      expect(SIMULATED_STRING_VALUES["OperationResponse.status"].values).toContain(operation.status);
      expect(SIMULATED_STRING_VALUES["OperationResponse.job_kind"].values).toContain(operation.job_kind);
      if (operation.diagnostic) expect(SIMULATED_STRING_VALUES["OperationResponse.diagnostic.code"].values).toContain(operation.diagnostic.code);
    }
    expect(SIMULATED_STRING_VALUES["WorkspaceResponse.state"].values).toContain(TEST_WORKSPACE.state);
    expect(SIMULATED_STRING_VALUES["UploadRevisionResponse.input_completeness"].values).toContain(TEST_UPLOAD_FULL.input_completeness);
    expect(SIMULATED_STRING_VALUES["SubmitAcceptedResponse.state"].values).toContain(TEST_SUBMIT_ACCEPTED.state);
    const anomalyCode = ARCHIVE_PLAN_NEEDS_CONFIRMATION.anomalies[0]?.issue_code;
    expect(SIMULATED_STRING_VALUES["ArchivePreviewAnomalyResponse.issue_code"].values).toContain(anomalyCode);
    expect(SIMULATED_STRING_VALUES["AppendArchiveAnomalyResolutionRequest.issue_code"].values).toContain(anomalyCode);
    expect(SIMULATED_STRING_VALUES["PreviewArchivePlanResponse.confirmation_requirements"].values).toContain(ARCHIVE_PLAN_NEEDS_CONFIRMATION.confirmation_requirements[0]);
    for (const plan of [ARCHIVE_PLAN_READY, ARCHIVE_PLAN_NEEDS_CONFIRMATION]) {
      for (const blocker of plan.blockers) expect(SIMULATED_STRING_VALUES["PreviewArchivePlanResponse.blockers"].values).toContain(blocker);
    }
    for (const candidate of [TEST_ARCHIVE_CANDIDATES, TEST_ARCHIVE_CANDIDATES_BLOCKED]) {
      for (const blocker of candidate.blockers) expect(SIMULATED_STRING_VALUES["ArchiveCandidatesResponse.blockers"].values).toContain(blocker);
    }
    expect(SIMULATED_STRING_VALUES["ArchiveCandidatesResponse.blockers"].values).toContain(TEST_ARCHIVE_CANDIDATES_BLOCKED.blockers[0]);
    for (const event of [TEST_ARCHIVE_CONFIRM_EVENT, TEST_ARCHIVE_ANOMALY_EVENT]) {
      expect(SIMULATED_STRING_VALUES["ArchiveAuditEventResponse.action"].values).toContain(event.action);
      expect(SIMULATED_STRING_VALUES["ArchiveAuditEventResponse.subject_kind"].values).toContain(event.subject_kind);
      expect(SIMULATED_STRING_VALUES["ArchiveAuditEventResponse.issue_code"].values).toContain(event.issue_code ?? null);
    }
    for (const node of [...HISTORY_PAGE_ONE.nodes, ...HISTORY_PAGE_TWO.nodes]) {
      expect(SIMULATED_STRING_VALUES["HistoryNodeResponse.eligibility_note"].values).toContain("eligibility_note" in node ? node.eligibility_note : null);
    }
    for (const response of Object.values(HISTORY_COMPARE_STATUS_SCENARIOS)) {
      expect(SIMULATED_STRING_VALUES["HistoryCompareResultResponse.status"].values).toContain(response.status);
      if (response.diagnostic) expect(SIMULATED_STRING_VALUES["HistoryCompareDiagnosticResponse.code"].values).toContain(response.diagnostic.code);
    }
  });

  it("keeps operation and workspace labels aligned with the sourced values", () => {
    expect(Object.keys(OPERATION_STATUS_COPY).sort()).toEqual([...SIMULATED_STRING_VALUES["OperationResponse.status"].values].sort());
    expect(Object.keys(WORKSPACE_STATE_COPY).sort()).toEqual([...SIMULATED_STRING_VALUES["WorkspaceResponse.state"].values].sort());
  });

  it("keeps every simulated History node within the backend node rules", () => {
    // Contract source: vnext/backend/src/gateway_backend/application/history/contracts.py:108-113.
    const pages = [HISTORY_PAGE_ONE, HISTORY_PAGE_TWO, TEST_HISTORY_CURSOR_FIRST, TEST_HISTORY_CURSOR_SECOND];
    for (const page of pages) {
      for (const node of page.nodes) {
        if (node.node_kind === "BASELINE_NODE") {
          expect(node.baseline_kind, `${node.ref_id} baseline_kind`).toBeDefined();
          expect(node).not.toHaveProperty("review_status");
          expect(node).not.toHaveProperty("archive_disposition");
          expect(node.identity_exception).not.toBe(true);
        } else if (node.node_kind === "SUBMISSION") {
          expect(node.review_status, `${node.ref_id} review_status`).toBeDefined();
          expect(node).not.toHaveProperty("baseline_kind");
        }
      }
    }
  });

  it("keeps the needs-confirmation archive plan within backend preview rules (B3 probe target)", () => {
    // Contract source: vnext/backend/src/gateway_backend/application/archive/queries.py:136-200:
    // can_start = selected && !blockers && audit_valid; before any confirmation is appended,
    // confirmation_requirements is non-empty and audit is invalid, so can_start must be false.
    // Negative probe (§9 B3): restoring can_start:true on this fixture must fail here.
    expect(ARCHIVE_PLAN_NEEDS_CONFIRMATION.confirmation_requirements.length + ARCHIVE_PLAN_NEEDS_CONFIRMATION.anomalies.length).toBeGreaterThan(0);
    expect(ARCHIVE_PLAN_NEEDS_CONFIRMATION.audit_validity).toBe(false);
    expect(ARCHIVE_PLAN_NEEDS_CONFIRMATION.can_start).toBe(false);
    expect(ARCHIVE_PLAN_NEEDS_CONFIRMATION.blockers).toEqual([]);
    expect(ARCHIVE_PLAN_READY.can_start).toBe(true);
    expect(ARCHIVE_PLAN_READY.audit_validity).toBe(true);
    // Q17: a confirmed preview keeps the selection, digest, requirements, and every anomaly.
    expect(ARCHIVE_PLAN_READY.selected).not.toBeNull();
    expect(ARCHIVE_PLAN_READY.selection_subject_digest).toBe("sha256:selection-subject");
    expect(ARCHIVE_PLAN_READY.confirmation_requirements[0]).toBe(ARCHIVE_PLAN_READY.selection_subject_digest);
    expect(ARCHIVE_PLAN_READY.anomalies.map((anomaly) => anomaly.subject_digest)).toEqual(["sha256:anomaly"]);
    // Negative probe (§5 N3): replacing confirmation_requirements with [] must fail here.
  });
  it("keeps every archive preview state consistent with the Q17 start rules", () => {
    const blockedPlan = { ...ARCHIVE_PLAN_NEEDS_CONFIRMATION, blockers: ["ACTIVE_SUBMIT_ATTEMPT"] };
    const plans = [ARCHIVE_PLAN_READY, ARCHIVE_PLAN_NEEDS_CONFIRMATION, blockedPlan];
    for (const plan of plans) {
      if (plan.selection_subject_digest) expect(plan.confirmation_requirements).toContain(plan.selection_subject_digest);
      if (!plan.audit_validity) expect(plan.can_start).toBe(false);
      if (plan.can_start) {
        expect(plan.selected).not.toBeNull();
        expect(plan.audit_validity).toBe(true);
        expect(plan.blockers).toEqual([]);
        expect(plan.anomalies.every((anomaly) => plan.confirmation_requirements.includes(anomaly.subject_digest))).toBe(true);
      }
    }
  });
  it("enforces the request-side constraints for every write route in one place (Q17)", () => {
    const keyRoutes = [
      "/v1/workspaces/workspace-fe2b/upload-revisions",
      "/v1/workspaces/workspace-fe2b/preview-operations",
      "/v1/workspaces/workspace-fe2b/submit-attempts",
      "/v1/submissions/submission-1/review-events",
      "/v1/history-compares",
      "/v1/archive-confirmations",
      "/v1/archive-anomaly-resolutions",
      "/v1/archives",
    ];
    for (const path of keyRoutes) {
      expect(validateSimulatedRequest({ method: "POST", url: new URL("http://local" + path), headers: {} }), path)
        .toEqual({ code: "REQUEST_VALIDATION_FAILED", message: "缺少 Idempotency-Key" });
      expect(validateSimulatedRequest({ method: "POST", url: new URL("http://local" + path), headers: { "Idempotency-Key": "key-1" } }), path).toBeNull();
    }
    const workspaces = new URL("http://local/v1/workspaces");
    expect(validateSimulatedRequest({ method: "POST", url: workspaces, headers: { "idempotency-key": "key-1" } }))
      .toEqual({ code: "REQUEST_VALIDATION_FAILED", message: "POST /v1/workspaces 不接受 Idempotency-Key" });
    expect(validateSimulatedRequest({ method: "POST", url: workspaces, headers: {} })).toBeNull();
    const audit = new URL("http://local/v1/archive-audit-events?subject_kind=CONFIRM_SELECTION&subject_digest=sha256:selection-subject");
    expect(validateSimulatedRequest({ method: "GET", url: audit, headers: {} })).toBeNull();
    expect(validateSimulatedRequest({ method: "GET", url: new URL("http://local/v1/archive-audit-events?subject_kind=CONFIRM_SELECTION"), headers: {} }))
      .toEqual({ code: "REQUEST_VALIDATION_FAILED", message: "缺少 subject_kind 或 subject_digest" });
    expect(validateSimulatedRequest({ method: "GET", url: new URL("http://local/v1/archive-audit-events?subject_digest=sha256:selection-subject"), headers: {} }))
      .toEqual({ code: "REQUEST_VALIDATION_FAILED", message: "缺少 subject_kind 或 subject_digest" });
  });
});
