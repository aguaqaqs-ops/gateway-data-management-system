import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { components } from "../api/generated/openapi";
type HistoryNode = components["schemas"]["HistoryNodeResponse"];
import {
  ARCHIVE_PLAN_NEEDS_CONFIRMATION, DISPOSITION_D5_NODE, DISPOSITION_HEAD, DISPOSITION_REVIEW_FACTS, DISPOSITION_SCENARIO_BASELINES, DISPOSITION_SCENARIO_NODES,
  HISTORY_PAGE_ONE, HISTORY_PAGE_TWO, HISTORY_COMPARE_STATUS_SCENARIOS, MANUAL_RECOVERY_TO_FAILED,
  MANUAL_RECOVERY_TO_SUCCESS, SIMULATED_ERROR_RESPONSES, SIMULATED_STRING_VALUES, TEST_ARCHIVE_ANOMALY_EVENT, TEST_ARCHIVE_CONFIRM_EVENT,
  ARCHIVE_PLAN_READY, COMPLETE_RESPONSE_SCENARIOS, OPERATION_TERMINAL_RESPONSES, TEST_ARCHIVE_CANDIDATES, TEST_ARCHIVE_CANDIDATES_BLOCKED,
  TEST_HISTORY_CURSOR_FIRST, TEST_HISTORY_CURSOR_SECOND, TEST_OPERATION_RUNNING, TEST_OPERATION_SUCCEEDED, TEST_SUBMIT_ACCEPTED, TEST_UPLOAD_FULL, TEST_WORKSPACE, WORKSPACE_RESPONSE, WRITE_SCENARIO_COVERAGE, validateSimulatedRequest,
} from "./simulated-api";
import { OPERATION_STATUS_COPY } from "../view-model/operation-status-copy";
import { WORKSPACE_STATE_COPY } from "../view-model/workspace-state-copy";
import { bundleErrorTitle } from "../bundle/local-bundle";

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
          if ("eligibility_note" in node && node.eligibility_note) {
            expect(node.review_status, `${node.ref_id} eligibility_note only on APPROVED`).toBe("APPROVED");
          }
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

  it("gives every OpenAPI-listed bundle error a frontend copy (B5)", async () => {
    const openapi = JSON.parse(await readFile(resolve(process.cwd(), "openapi.json"), "utf8")) as {
      paths: Record<string, Record<string, { responses?: Record<string, { description?: string }> }>>;
    };
    // §5.3 bundle codes: Preview 503 BUNDLE_INTEGRITY_FAILURE; History 404
    // ARTIFACT_UNAVAILABLE and 503 BUNDLE_INTEGRITY_FAILURE. Every code listed
    // on the two routes needs copy; the §5.3 codes additionally need a
    // simulated scenario (parsed by the generic snapshot test above).
    const simulatedByRoute: Record<string, string[]> = {
      "/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}/bundle": [
        "SERVICE_NOT_READY",
        "BUNDLE_INTEGRITY_FAILURE",
      ],
      "/v1/history-compares/{operation_id}/bundle": ["ARTIFACT_UNAVAILABLE", "BUNDLE_INTEGRITY_FAILURE"],
    };
    for (const [route, simulated] of Object.entries(simulatedByRoute)) {
      const responses = openapi.paths[route]?.get?.responses ?? {};
      const codes = Object.entries(responses)
        .filter(([status]) => status !== "200")
        .flatMap(([, response]) => (response.description ?? "").split(",").map((code) => code.trim()).filter(Boolean))
        .filter((code) => /^[A-Z][A-Z0-9_]*$/.test(code));
      expect(codes.length).toBeGreaterThan(0);
      for (const code of codes) {
        expect(bundleErrorTitle(code), `${route} ${code}`).toBeDefined();
      }
      for (const code of simulated) {
        expect(codes, `${route} documents ${code}`).toContain(code);
        expect(
          SIMULATED_ERROR_RESPONSES.some((entry) => entry.route === route && entry.body.code === code),
          `${route} ${code} simulated`,
        ).toBe(true);
      }
    }
    // §2.3 changed codes are covered by the generic snapshot-parsing test above.
    for (const code of ["BASELINE_VERSION_CONFLICT", "ARCHIVE_CLOSED", "BUNDLE_INTEGRITY_FAILURE", "ARTIFACT_UNAVAILABLE"]) {
      expect(SIMULATED_ERROR_RESPONSES.some((entry) => entry.body.code === code), code).toBe(true);
    }
    expect(
      SIMULATED_ERROR_RESPONSES.some((entry) => entry.route === "/v1/submissions/{submission_id}/review" && entry.status === 403),
      "review 403",
    ).toBe(true);
    expect(
      SIMULATED_ERROR_RESPONSES.some((entry) => entry.route === "/v1/submissions/{submission_id}/review" && entry.status === 404),
      "review 404",
    ).toBe(true);
  });

  it("keeps every disposition scenario within the backend reachability rules (B7, §5.3)", () => {
    const nodes = [...DISPOSITION_SCENARIO_NODES, ...DISPOSITION_SCENARIO_BASELINES];
    const archivedByResult = new Map<string, string[]>();
    for (const node of nodes) {
      if (node.node_kind === "BASELINE_NODE") {
        expect(node).not.toHaveProperty("review_status");
        continue;
      }
      expect(node.node_kind).toBe("SUBMISSION");
      // Dispositions only appear on APPROVED submissions.
      if (node.submission_disposition) {
        expect(node.review_status, `${node.ref_id} disposition requires APPROVED`).toBe("APPROVED");
      }
      if (node.eligibility_note) {
        expect(node.review_status, `${node.ref_id} eligibility_note only on APPROVED`).toBe("APPROVED");
      }
      if (node.submission_disposition === "ARCHIVED_BASELINE") {
        expect(node.disposition_source_kind, `${node.ref_id} archive source`).toBe("ARCHIVE");
        expect(node.disposition_result_id, `${node.ref_id} result`).toBeTruthy();
        expect(node.closure ?? null, `${node.ref_id} no closure`).toBeNull();
        expect(node.disposition_source_kind, `${node.ref_id} not manual`).not.toBe("MANUAL_CLOSE");
        const baseline = nodes.find((candidate) => candidate.ref_id === node.promoted_baseline_node_id);
        expect(baseline, `${node.ref_id} promoted baseline`).toBeDefined();
        expect(baseline?.node_kind).toBe("BASELINE_NODE");
        expect(baseline?.baseline_kind).toBe("ARCHIVED_SUBMISSION");
        const members = archivedByResult.get(node.disposition_result_id ?? "") ?? [];
        archivedByResult.set(node.disposition_result_id ?? "", [...members, node.ref_id]);
      }
      if (node.submission_disposition === "CLOSED_NOT_ARCHIVED" && node.disposition_source_kind === "ARCHIVE") {
        expect(node.disposition_result_id, `${node.ref_id} result`).toBeTruthy();
        expect(node.closure ?? null, `${node.ref_id} no closure`).toBeNull();
      }
      if (node.submission_disposition === "CLOSED_NOT_ARCHIVED" && node.disposition_source_kind === "MANUAL_CLOSE") {
        expect(node.disposition_result_id ?? null, `${node.ref_id} no result`).toBeNull();
        expect(node.closure, `${node.ref_id} closure`).toBeDefined();
        expect(node.closure?.closed_by, `${node.ref_id} closed_by`).toBeTruthy();
        expect(node.closure?.reason, `${node.ref_id} reason`).toBeTruthy();
      }
    }
    // One archive result produces at most one ARCHIVED_BASELINE.
    for (const [resultId, members] of archivedByResult) {
      expect(members.length, `archive result ${resultId}`).toBeLessThanOrEqual(1);
    }
    // The shared scenario array carries no D5 shape: D5 lives only in D5 case
    // data (DISPOSITION_D5_NODE), asserted below.
    const defensive = DISPOSITION_SCENARIO_NODES.filter((node) => !node.submission_disposition);
    expect(defensive.map((node) => node.ref_id)).toEqual([]);
    expect(DISPOSITION_D5_NODE.eligibility_note).toBe("NOT_CANDIDATE_BASE_ADVANCED");
    expect(DISPOSITION_D5_NODE.submission_disposition ?? null).toBeNull();
    expect(DISPOSITION_D5_NODE.review_status).toBe("APPROVED");
    // Review facts agree with the History nodes for the same submission.
    for (const facts of DISPOSITION_REVIEW_FACTS) {
      const node = DISPOSITION_SCENARIO_NODES.find((candidate) => candidate.ref_id === facts.submission_id);
      expect(node, `${facts.submission_id} history node`).toBeDefined();
      expect(node?.submission_disposition).toBe(facts.submission_disposition?.disposition);
      expect(node?.disposition_source_kind).toBe(facts.submission_disposition?.source_kind);
      expect(node?.disposition_result_id ?? null).toBe(facts.submission_disposition?.result_id ?? null);
      expect(node?.closure ?? null).toEqual(facts.submission_disposition?.closure ?? null);
    }
    // Disposed submissions are not any workspace's active submission (the W10
    // stale-workspace race is constructed and documented in the e2e spec).
    const disposed = new Set(
      DISPOSITION_SCENARIO_NODES.filter((node) => node.submission_disposition).map((node) => node.ref_id),
    );
    for (const fixture of [WORKSPACE_RESPONSE, TEST_WORKSPACE]) {
      if (fixture.active_submission_id) {
        expect(disposed.has(fixture.active_submission_id), fixture.active_submission_id).toBe(false);
      }
    }
  });

  it("keeps every simulated History dataset reachable (F4, projection.py:216)", () => {
    // Contract source: vnext/backend/src/gateway_backend/application/history/projection.py:210-218 —
    // the note is present iff the node is APPROVED and its parent baseline is
    // not the head, independent of any disposition. An APPROVED submission
    // whose parent is not the head must carry a disposition, except the
    // explicitly listed D5 refs (DC89-unreachable, defensive).
    type HistoryDataset = {
      name: string;
      headId: string;
      nodes: HistoryNode[];
      d5: string[];
    };
    const mergedShared: HistoryNode[] = [...HISTORY_PAGE_ONE.nodes, ...HISTORY_PAGE_TWO.nodes];
    const mergedCursor: HistoryNode[] = [...TEST_HISTORY_CURSOR_FIRST.nodes, ...TEST_HISTORY_CURSOR_SECOND.nodes];
    const scenario = [...DISPOSITION_SCENARIO_NODES, ...DISPOSITION_SCENARIO_BASELINES] ;
    const datasets: HistoryDataset[] = [
      { name: "HISTORY_PAGE_ONE", headId: HISTORY_PAGE_ONE.head.node_id, nodes: HISTORY_PAGE_ONE.nodes, d5: [] },
      { name: "HISTORY_PAGE_TWO", headId: HISTORY_PAGE_TWO.head.node_id, nodes: HISTORY_PAGE_TWO.nodes, d5: [] },
      { name: "merged shared pages", headId: HISTORY_PAGE_ONE.head.node_id, nodes: mergedShared, d5: [] },
      { name: "TEST_HISTORY_CURSOR_FIRST", headId: TEST_HISTORY_CURSOR_FIRST.head.node_id, nodes: TEST_HISTORY_CURSOR_FIRST.nodes, d5: [] },
      // submission-1 is the documented D5 shape (APPROVED + note, no
      // disposition) kept for the cursor-pagination display test.
      { name: "TEST_HISTORY_CURSOR_SECOND", headId: TEST_HISTORY_CURSOR_SECOND.head.node_id, nodes: TEST_HISTORY_CURSOR_SECOND.nodes, d5: ["submission-1"] },
      { name: "merged cursor pages", headId: TEST_HISTORY_CURSOR_FIRST.head.node_id, nodes: mergedCursor, d5: ["submission-1"] },
      { name: "disposition scenarios", headId: DISPOSITION_HEAD.node_id, nodes: scenario, d5: [] },
      // D5 case data: the only dataset allowed to carry the D5 shape.
      { name: "D5 case", headId: DISPOSITION_HEAD.node_id, nodes: [...scenario, DISPOSITION_D5_NODE] , d5: ["d5"] },
    ];
    for (const dataset of datasets) {
      for (const node of dataset.nodes) {
        if (node.node_kind === "BASELINE_NODE") continue;
        const parentId = node.parent?.ref_id ?? null;
        const note = "eligibility_note" in node ? node.eligibility_note : null;
        if (note) {
          expect(node.review_status, `${dataset.name} ${node.ref_id} note only on APPROVED`).toBe("APPROVED");
          expect(parentId, `${dataset.name} ${node.ref_id} note only off-head`).not.toBe(dataset.headId);
        } else if (node.review_status === "APPROVED" && parentId !== dataset.headId) {
          expect(note ?? null, `${dataset.name} ${node.ref_id} off-head APPROVED keeps the note`).not.toBeNull();
        }
        if (node.review_status === "APPROVED" && parentId !== dataset.headId && !dataset.d5.includes(node.ref_id)) {
          expect(node.submission_disposition ?? null, `${dataset.name} ${node.ref_id} off-head APPROVED is disposed`).not.toBeNull();
        }
      }
    }
    // Off-head APPROVED submissions without a disposition exist only as the
    // listed D5 refs: injecting one more must fail here (probe Q4).
    for (const dataset of datasets) {
      const undisposed = dataset.nodes.filter((node) =>
        node.node_kind === "SUBMISSION" && node.review_status === "APPROVED"
        && (node.parent?.ref_id ?? null) !== dataset.headId && !(node.submission_disposition ?? null));
      expect(undisposed.map((node) => node.ref_id).sort(), `${dataset.name} D5 refs`).toEqual([...dataset.d5].sort());
    }
  });

  it("keeps the archive baseline chain connected with the head at the tip (F4)", () => {
    // The archived baselines form one chain and the head is its end; a
    // promoted baseline's parent equals the archiving submission's parent;
    // one parent baseline yields at most one ARCHIVED_BASELINE; archive
    // siblings closed by the same result share the archived parent.
    const checkChain = (name: string, headId: string, nodes: HistoryNode[]) => {
      const byId = new Map(nodes.map((node) => [node.ref_id, node]));
      const archived = nodes.filter((node) =>
        node.node_kind === "SUBMISSION" && node.submission_disposition === "ARCHIVED_BASELINE");
      const archivedByParent = new Map<string, string[]>();
      for (const node of archived) {
        const parentId = node.parent?.ref_id ?? "";
        const members = archivedByParent.get(parentId) ?? [];
        archivedByParent.set(parentId, [...members, node.ref_id]);
        const promoted = node.promoted_baseline_node_id ? byId.get(node.promoted_baseline_node_id) : undefined;
        expect(promoted, `${name} ${node.ref_id} promoted baseline present`).toBeDefined();
        expect(promoted?.parent?.ref_id, `${name} ${node.ref_id} promoted parent matches`).toBe(parentId);
      }
      for (const [parentId, members] of archivedByParent) {
        expect(members.length, `${name} parent ${parentId} single ARCHIVED_BASELINE`).toBeLessThanOrEqual(1);
      }
      const closedByResult = new Map<string, typeof nodes>();
      for (const node of nodes) {
        if (node.node_kind === "SUBMISSION" && node.submission_disposition === "CLOSED_NOT_ARCHIVED"
          && node.disposition_source_kind === "ARCHIVE") {
          const members = closedByResult.get(node.disposition_result_id ?? "") ?? [];
          closedByResult.set(node.disposition_result_id ?? "", [...members, node]);
        }
      }
      for (const [resultId, members] of closedByResult) {
        const archivedSibling = archived.find((node) => node.disposition_result_id === resultId);
        expect(archivedSibling, `${name} result ${resultId} has its archived submit`).toBeDefined();
        for (const member of members) {
          expect(member.parent?.ref_id, `${name} ${member.ref_id} shares the archived parent`).toBe(archivedSibling?.parent?.ref_id);
        }
      }
      // Walk the baseline chain from the head; every archived baseline must be
      // reachable and the archived submissions' parents must lie on it.
      const baselineParents = new Map<string, string | null>();
      for (const node of nodes) {
        if (node.node_kind === "BASELINE_NODE" && node.baseline_kind === "ARCHIVED_SUBMISSION") {
          baselineParents.set(node.ref_id, node.parent?.ref_id ?? null);
        }
      }
      if (baselineParents.size > 0) {
        const chain = new Set<string>();
        let current: string | null = headId;
        while (current) {
          chain.add(current);
          const next = baselineParents.get(current);
          current = next === undefined ? null : next;
        }
        for (const parentId of archivedByParent.keys()) {
          expect(chain.has(parentId), `${name} archive parent ${parentId} on the head chain`).toBe(true);
        }
        for (const node of archived) {
          const promoted = node.promoted_baseline_node_id ?? "";
          expect(chain.has(promoted), `${name} promoted ${promoted} on the head chain`).toBe(true);
        }
      }
    };
    const mergedShared: HistoryNode[] = [...HISTORY_PAGE_ONE.nodes, ...HISTORY_PAGE_TWO.nodes];
    checkChain("merged shared pages", HISTORY_PAGE_ONE.head.node_id, mergedShared);
    const scenario = [...DISPOSITION_SCENARIO_NODES, ...DISPOSITION_SCENARIO_BASELINES] ;
    checkChain("disposition scenarios", DISPOSITION_HEAD.node_id, scenario);
  });
});
