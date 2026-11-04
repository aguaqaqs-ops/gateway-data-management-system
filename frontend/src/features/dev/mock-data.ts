import type { components } from "../api/generated/openapi";

type Schemas = components["schemas"];

export const SIMULATED_STRING_VALUES = {
  "OperationResponse.status": {
    values: ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "SUPERSEDED", "MANUAL_RECOVERY_REQUIRED"],
    source: "vnext/backend/src/gateway_backend/operations/contracts.py:OperationStatus",
  },
  "HistoryCompareResultResponse.status": {
    values: ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"],
    source: "vnext/backend/src/gateway_backend/http/schemas/history.py:HistoryCompareResultResponse.status",
  },
  "OperationResponse.job_kind": {
    values: ["backend-vnext/preview", "backend-vnext/submit", "backend-vnext/history-compare"],
    source: "preview_jobs.py:PREVIEW_JOB_KIND; submission/job_payload.py:SUBMIT_JOB_KIND; application/history/contracts.py:HISTORY_COMPARE_JOB_KIND",
  },
  "OperationResponse.diagnostic.code": {
    values: ["r5.manual_recovery_required", "R5.RECOVERY_AUTHORIZED"],
    source: "vnext/backend/src/gateway_backend/application/recovery.py:DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED; operations/state.py:DIAGNOSTIC_OPERATOR_RECOVERY_AUTHORIZED",
  },
  "HistoryCompareDiagnosticResponse.code": {
    values: ["HISTORY_RULESET_VERSION_MISMATCH"],
    source: "vnext/backend/src/gateway_backend/application/history/contracts.py:HistoryCompareDiagnosticCode",
  },
  "WorkspaceResponse.state": {
    values: ["OPEN", "CLOSED"],
    source: "vnext/backend/src/gateway_backend/domain/workspace/models.py:WorkspaceState",
  },
  "UploadRevisionResponse.input_completeness": {
    values: ["FULL", "MODIFIED_ONLY"],
    source: "vnext/backend/src/gateway_backend/domain/workspace/models.py:InputCompleteness",
  },
  "SubmitAcceptedResponse.state": {
    values: ["PREPARED"],
    source: "vnext/backend/src/gateway_backend/domain/submission/models.py:SubmitAttemptState.PREPARED",
  },
  "ArchivePreviewAnomalyResponse.issue_code": {
    values: ["APPROVED_SIBLING_EXCLUDED", "PROJECT_IDENTITY_EXCEPTION"],
    source: "vnext/backend/src/gateway_backend/application/archive/queries.py:*_ISSUE",
  },
  "AppendArchiveAnomalyResolutionRequest.issue_code": {
    values: ["APPROVED_SIBLING_EXCLUDED", "PROJECT_IDENTITY_EXCEPTION"],
    source: "vnext/backend/src/gateway_backend/application/archive/queries.py:*_ISSUE",
  },
  "PreviewArchivePlanResponse.blockers": {
    values: ["ACTIVE_SUBMIT_ATTEMPT", "ARCHIVE_INTEGRITY_FAILURE"],
    source: "vnext/backend/src/gateway_backend/application/archive/snapshot.py:collect_repository_submit_blockers",
  },
  "ArchiveCandidatesResponse.blockers": {
    values: ["ACTIVE_SUBMIT_ATTEMPT", "ARCHIVE_INTEGRITY_FAILURE"],
    source: "vnext/backend/src/gateway_backend/application/archive/snapshot.py:collect_repository_submit_blockers",
  },
  "PreviewArchivePlanResponse.confirmation_requirements": {
    values: ["sha256:selection-subject"],
    source: "vnext/backend/src/gateway_backend/application/archive/queries.py:selection_subject_digest",
  },
  "ArchiveAuditEventResponse.subject_kind": {
    values: ["CONFIRM_SELECTION", "APPROVED_SIBLING_EXCLUDED", "PROJECT_IDENTITY_EXCEPTION"],
    source: "vnext/backend/src/gateway_backend/domain/archive/models.py:ArchiveSubjectKind",
  },
  "ArchiveAuditEventResponse.action": {
    values: ["CONFIRM", "REVOKE", "ACKNOWLEDGE_EXCLUSION", "ACKNOWLEDGE_IDENTITY_EXCEPTION"],
    source: "vnext/backend/src/gateway_backend/domain/archive/models.py:ArchiveConfirmationAction, ArchiveAnomalyResolutionAction",
  },
  "ArchiveAuditEventResponse.issue_code": {
    values: ["APPROVED_SIBLING_EXCLUDED", "PROJECT_IDENTITY_EXCEPTION", null],
    source: "vnext/backend/src/gateway_backend/application/archive/queries.py:*_ISSUE",
  },
  "HistoryNodeResponse.eligibility_note": {
    values: ["NOT_CANDIDATE_BASE_ADVANCED", null],
    source: "vnext/backend/src/gateway_backend/application/history/contracts.py:HistoryEligibilityNote",
  },
} as const;

export const WORKSPACE_RESPONSE = {
  workspace_id: "workspace-fe2b",
  gateway_device_external_key: "gateway-17",
  business_project_id: "project-42",
  state: "OPEN",
  generation: 3,
  optimistic_version: 12,
  created_at: "2026-11-03T08:00:00Z",
  updated_at: "2026-11-03T09:14:00Z",
  current_upload_revision_id: "upload-fe2b-3",
  current_preview_result_id: "preview-full",
} satisfies Schemas["WorkspaceResponse"];

export const WORKSPACE_CREATED = { status: 201, body: WORKSPACE_RESPONSE } as const;
export const WORKSPACE_ALREADY_EXISTS = { status: 200, body: WORKSPACE_RESPONSE } as const;

export const HISTORY_PAGE_ONE = {
  head: { node_id: "fe2a-history-ref-1", commit_id: "commit-baseline-1", version: 21 },
  nodes: [
    {
      ref_kind: "baseline_node", ref_id: "fe2a-history-ref-1", node_kind: "BASELINE_NODE", baseline_kind: "ARCHIVED_SUBMISSION",
      commit_id: "commit-baseline-1", created_at: "2026-11-01T13:00:00Z", parent: { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-0" },
      identity_exception: false,
    },
    {
      ref_kind: "submission", ref_id: "fe2a-history-ref-2", node_kind: "SUBMISSION", commit_id: "commit-submission-2",
      created_at: "2026-11-02T09:10:00Z", parent: { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-1" },
      identity_exception: false, review_status: "PENDING",
    },
  ],
  next_cursor: "history-page-2",
} satisfies Schemas["HistoryListResponse"];

export const HISTORY_PAGE_TWO = {
  head: HISTORY_PAGE_ONE.head,
  nodes: [
    {
      ref_kind: "baseline_node", ref_id: "fe2a-history-ref-0", node_kind: "BASELINE_NODE", baseline_kind: "INITIAL",
      commit_id: "commit-baseline-0", created_at: "2026-10-30T09:00:00Z", parent: null,
      identity_exception: false,
    },
    {
      ref_kind: "submission", ref_id: "fe2a-history-ref-old", node_kind: "SUBMISSION", commit_id: "commit-submission-old",
      created_at: "2026-10-31T09:10:00Z", parent: { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-0" },
      eligibility_note: "NOT_CANDIDATE_BASE_ADVANCED", identity_exception: true, review_status: "APPROVED",
    },
  ],
  next_cursor: null,
} satisfies Schemas["HistoryListResponse"];

export const REVIEW_FACTS = {
  submission_id: "fe2a-history-ref-2",
  status: "PENDING",
  review_version: 4,
  updated_by: "submitter",
  updated_at: "2026-11-02T09:10:00Z",
  identity_exception: false,
  events: [{ sequence: 1, event_kind: "SUBMISSION_FINALIZED", to_status: "PENDING", actor_id: "submitter", occurred_at: "2026-11-02T09:10:00Z" }],
} satisfies Schemas["ReviewFactsResponse"];

export const HISTORY_COMPARE_REQUEST = {
  nodes: [
    { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-0" },
    { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-1" },
    { ref_kind: "submission", ref_id: "fe2a-history-ref-2" },
  ],
} satisfies Schemas["HistoryCompareAcceptRequest"];

export const HISTORY_COMPARE_ACCEPT_BODY = {
  operation_id: "history-compare-fe2b-1",
  status: "QUEUED",
  replayed: false,
} satisfies Schemas["HistoryCompareAcceptResponse"];

export const HISTORY_COMPARE_ACCEPTED = { status: 202, body: HISTORY_COMPARE_ACCEPT_BODY } as const;
// The replay uses the response body accepted for the first request, as the HTTP idempotency contract requires.
export const HISTORY_COMPARE_REPLAY = { status: 200, body: HISTORY_COMPARE_ACCEPT_BODY } as const;

export const HISTORY_COMPARE_QUEUED = {
  operation_id: "history-compare-fe2b-1", status: "QUEUED", diagnostic: null,
} satisfies Schemas["HistoryCompareResultResponse"];

export const HISTORY_COMPARE_FAILED = {
  operation_id: "history-compare-fe2b-failed",
  status: "FAILED",
  diagnostic: { code: "HISTORY_RULESET_VERSION_MISMATCH", message: "frozen comparison ruleset digest does not match runtime ruleset" },
  result: null,
} satisfies Schemas["HistoryCompareResultResponse"];

export const HISTORY_COMPARE_CANCELLED = {
  operation_id: "history-compare-fe2b-cancelled", status: "CANCELLED", diagnostic: null, result: null,
} satisfies Schemas["HistoryCompareResultResponse"];

export const HISTORY_COMPARE_RUNNING = {
  operation_id: "history-compare-fe2b-1", status: "RUNNING", diagnostic: null,
} satisfies Schemas["HistoryCompareResultResponse"];

export const HISTORY_COMPARE_SUCCEEDED = {
  operation_id: "history-compare-fe2b-1",
  status: "SUCCEEDED",
  diagnostic: null,
  result: {
    bundle_digest: "sha256:5d22992d518dfd1e95cd8d7174a91fb2dad70e04a869757bf304e438f5b60b2c",
    completed_at: "2026-11-03T09:15:00Z",
    input: { nodes: HISTORY_COMPARE_REQUEST.nodes },
    pairs: [
      {
        pair_id: "fe2a-history-fixture-p0", before_commit: "commit-baseline-0", current_commit: "commit-baseline-1",
        before_ref: { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-0" },
        current_ref: { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-1" },
        comparison_digest: "sha256:2b774878059e5090568163242cae87e737b056bff7c309206108d1fc3d79a315",
        risk_digest: "sha256:582612808cb7bcff871c36a65ef61942b106fc95e397e28b70ad181148223d1f",
        surface_digest: "sha256:b8655d480b64a4aac7a934bad84edc6afd0536a8e0ab6e19fbda2ac369961f5f", record_count: 4,
      },
      {
        pair_id: "fe2a-history-fixture-p1", before_commit: "commit-baseline-1", current_commit: "commit-submission-2",
        before_ref: { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-1" },
        current_ref: { ref_kind: "submission", ref_id: "fe2a-history-ref-2" },
        comparison_digest: "sha256:a4d362ecddeff4fd28aec475bb8486f3bfbe9c7722892664eb92064b3685acb5",
        risk_digest: "sha256:8de97b2af288d74b357001276ce5e4aa75ea20f101b98ed047f55c6ce8bb8d7f",
        surface_digest: "sha256:d2eebde995b72128cae4cb9bb5e6aac8ad4ba390453a11c15845205c5af1b332", record_count: 3,
      },
    ],
  },
} satisfies Schemas["HistoryCompareResultResponse"];

export const HISTORY_COMPARE_STATUS_SCENARIOS = {
  QUEUED: HISTORY_COMPARE_QUEUED,
  RUNNING: HISTORY_COMPARE_RUNNING,
  SUCCEEDED: HISTORY_COMPARE_SUCCEEDED,
  FAILED: HISTORY_COMPARE_FAILED,
  CANCELLED: HISTORY_COMPARE_CANCELLED,
} as const;

const OPERATION_FIELDS = {
  optimistic_version: 3,
  created_at: "2026-11-03T09:00:00Z",
  started_at: "2026-11-03T09:00:01Z",
  completed_at: null,
  diagnostic: null,
} satisfies Omit<Schemas["OperationResponse"], "operation_id" | "job_kind" | "status">;

export const MANUAL_RECOVERY_TO_SUCCESS = [
  { ...OPERATION_FIELDS, optimistic_version: 3, operation_id: "operation-manual-success", job_kind: "backend-vnext/preview", status: "MANUAL_RECOVERY_REQUIRED", diagnostic: { code: "r5.manual_recovery_required", message: "preview recovery requires a runnable handler replay" } },
  { ...OPERATION_FIELDS, optimistic_version: 4, operation_id: "operation-manual-success", job_kind: "backend-vnext/preview", status: "RUNNING" },
  { ...OPERATION_FIELDS, optimistic_version: 5, operation_id: "operation-manual-success", job_kind: "backend-vnext/preview", status: "SUCCEEDED", completed_at: "2026-11-03T09:04:00Z" },
] satisfies Schemas["OperationResponse"][];

export const MANUAL_RECOVERY_TO_FAILED = [
  { ...OPERATION_FIELDS, optimistic_version: 3, operation_id: "operation-manual-failed", job_kind: "backend-vnext/preview", status: "MANUAL_RECOVERY_REQUIRED", diagnostic: { code: "r5.manual_recovery_required", message: "preview recovery requires a runnable handler replay" } },
  { ...OPERATION_FIELDS, optimistic_version: 4, operation_id: "operation-manual-failed", job_kind: "backend-vnext/preview", status: "FAILED", completed_at: "2026-11-03T09:05:00Z", diagnostic: { code: "R5.RECOVERY_AUTHORIZED", message: "操作已人工确认终止" } },
] satisfies Schemas["OperationResponse"][];

export interface ApiErrorResponse {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

export const SIMULATED_ERROR_RESPONSES: ReadonlyArray<{
  route: string;
  method: "GET" | "POST";
  status: number;
  schema: "ErrorResponse";
  body: ApiErrorResponse;
}> = [
  { route: "/v1/history", method: "GET", status: 403, schema: "ErrorResponse", body: { code: "SCOPE_FORBIDDEN", message: "当前身份没有历史读取权限" } },
  { route: "/v1/operations/{operation_id}", method: "GET", status: 403, schema: "ErrorResponse", body: { code: "SCOPE_FORBIDDEN", message: "当前身份没有操作读取权限" } },
  { route: "/v1/workspaces", method: "POST", status: 403, schema: "ErrorResponse", body: { code: "SCOPE_FORBIDDEN", message: "当前身份没有创建工作区的权限" } },
  { route: "/v1/workspaces", method: "POST", status: 422, schema: "ErrorResponse", body: { code: "REQUEST_VALIDATION_FAILED", message: "工作区参数无效" } },
  { route: "/v1/workspaces", method: "POST", status: 503, schema: "ErrorResponse", body: { code: "SERVICE_NOT_READY", message: "工作区服务暂时不可用" } },
  { route: "/v1/workspaces/{workspace_id}/upload-revisions", method: "POST", status: 403, schema: "ErrorResponse", body: { code: "SCOPE_FORBIDDEN", message: "当前身份没有上传权限" } },
  { route: "/v1/workspaces/{workspace_id}/upload-revisions", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "WORKSPACE_VERSION_CONFLICT", message: "工作区版本已更新" } },
  { route: "/v1/workspaces/{workspace_id}/upload-revisions", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "IDEMPOTENCY_CONFLICT", message: "相同幂等键对应了不同上传" } },
  { route: "/v1/workspaces/{workspace_id}/preview-operations", method: "POST", status: 403, schema: "ErrorResponse", body: { code: "SCOPE_FORBIDDEN", message: "当前身份没有启动预览的权限" } },
  { route: "/v1/workspaces/{workspace_id}/preview-operations", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "WORKSPACE_VERSION_CONFLICT", message: "工作区版本已更新" } },
  { route: "/v1/workspaces/{workspace_id}/preview-operations", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "IDEMPOTENCY_CONFLICT", message: "相同幂等键对应了不同预览请求" } },
  { route: "/v1/workspaces/{workspace_id}/submit-attempts", method: "POST", status: 403, schema: "ErrorResponse", body: { code: "SCOPE_FORBIDDEN", message: "当前身份没有提交权限" } },
  { route: "/v1/workspaces/{workspace_id}/submit-attempts", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "WORKSPACE_VERSION_CONFLICT", message: "工作区版本已更新" } },
  { route: "/v1/workspaces/{workspace_id}/submit-attempts", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "IDEMPOTENCY_CONFLICT", message: "相同幂等键对应了不同提交请求" } },
  { route: "/v1/workspaces/{workspace_id}/submit-attempts", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "BASELINE_VERSION_CONFLICT", message: "当前基线已更新" } },
  { route: "/v1/submissions/{submission_id}/review-events", method: "POST", status: 403, schema: "ErrorResponse", body: { code: "SCOPE_FORBIDDEN", message: "当前身份没有审核权限" } },
  { route: "/v1/submissions/{submission_id}/review-events", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "REVIEW_VERSION_CONFLICT", message: "审核状态已更新" } },
  { route: "/v1/submissions/{submission_id}/review-events", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "IDEMPOTENCY_CONFLICT", message: "相同幂等键对应了不同审核请求" } },
  { route: "/v1/history-compares", method: "POST", status: 403, schema: "ErrorResponse", body: { code: "SCOPE_FORBIDDEN", message: "当前身份没有历史比较权限" } },
  { route: "/v1/history-compares", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "IDEMPOTENCY_CONFLICT", message: "相同幂等键对应了不同请求" } },
  { route: "/v1/history-compares", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "ADMISSION_CONFLICT", message: "历史比较请求与当前工作冲突" } },
  { route: "/v1/history-compares", method: "POST", status: 429, schema: "ErrorResponse", body: { code: "ADMISSION_LIMIT_REACHED", message: "历史比较请求已达到并发上限" } },
  { route: "/v1/archive-plan-preview", method: "POST", status: 403, schema: "ErrorResponse", body: { code: "SCOPE_FORBIDDEN", message: "当前身份没有预检归档方案的权限" } },
  { route: "/v1/archive-plan-preview", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "CANDIDATE_BINDING_CONFLICT", message: "所选提交与候选快照不匹配" } },
  { route: "/v1/archive-confirmations", method: "POST", status: 403, schema: "ErrorResponse", body: { code: "SCOPE_FORBIDDEN", message: "当前身份没有确认归档的权限" } },
  { route: "/v1/archive-confirmations", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "BASELINE_VERSION_CONFLICT", message: "当前基线已更新" } },
  { route: "/v1/archive-confirmations", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "ARCHIVE_AUDIT_VERSION_CONFLICT", message: "归档审计序号已更新" } },
  { route: "/v1/archive-confirmations", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "IDEMPOTENCY_CONFLICT", message: "相同幂等键对应了不同确认" } },
  { route: "/v1/archive-anomaly-resolutions", method: "POST", status: 403, schema: "ErrorResponse", body: { code: "SCOPE_FORBIDDEN", message: "当前身份没有处理归档异常的权限" } },
  { route: "/v1/archive-anomaly-resolutions", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "BASELINE_VERSION_CONFLICT", message: "当前基线已更新" } },
  { route: "/v1/archive-anomaly-resolutions", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "ARCHIVE_AUDIT_VERSION_CONFLICT", message: "归档审计序号已更新" } },
  { route: "/v1/archive-anomaly-resolutions", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "IDEMPOTENCY_CONFLICT", message: "相同幂等键对应了不同异常处理" } },
  { route: "/v1/archives", method: "POST", status: 403, schema: "ErrorResponse", body: { code: "SCOPE_FORBIDDEN", message: "当前身份没有归档主线的权限" } },
  { route: "/v1/archives", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "BASELINE_VERSION_CONFLICT", message: "当前基线已更新" } },
  { route: "/v1/archives", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "ARCHIVE_AUDIT_VERSION_CONFLICT", message: "归档审计序号已更新" } },
  { route: "/v1/archives", method: "POST", status: 409, schema: "ErrorResponse", body: { code: "IDEMPOTENCY_CONFLICT", message: "相同幂等键对应了不同归档请求" } },
  { route: "/v1/history-compares/{operation_id}", method: "GET", status: 503, schema: "ErrorResponse", body: { code: "HISTORY_INTEGRITY_FAILURE", message: "历史比较状态暂时不可用" } },
  { route: "/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}/bundle", method: "GET", status: 503, schema: "ErrorResponse", body: { code: "SERVICE_NOT_READY", message: "比较结果暂时不可用" } },
];

export const WRITE_SCENARIO_COVERAGE = [
  { method: "POST", route: "/v1/workspaces", outcomes: ["success:201", "success:200", "403:SCOPE_FORBIDDEN"] },
  { method: "POST", route: "/v1/workspaces/{workspace_id}/upload-revisions", outcomes: ["success:201", "403:SCOPE_FORBIDDEN", "409:WORKSPACE_VERSION_CONFLICT", "409:IDEMPOTENCY_CONFLICT"] },
  { method: "POST", route: "/v1/workspaces/{workspace_id}/preview-operations", outcomes: ["success:202", "403:SCOPE_FORBIDDEN", "409:WORKSPACE_VERSION_CONFLICT", "409:IDEMPOTENCY_CONFLICT"] },
  { method: "POST", route: "/v1/workspaces/{workspace_id}/submit-attempts", outcomes: ["success:202", "403:SCOPE_FORBIDDEN", "409:WORKSPACE_VERSION_CONFLICT", "409:BASELINE_VERSION_CONFLICT", "409:IDEMPOTENCY_CONFLICT"] },
  { method: "POST", route: "/v1/submissions/{submission_id}/review-events", outcomes: ["success:201", "403:SCOPE_FORBIDDEN", "409:REVIEW_VERSION_CONFLICT", "409:IDEMPOTENCY_CONFLICT"] },
  { method: "POST", route: "/v1/history-compares", outcomes: ["success:202", "replay:200", "403:SCOPE_FORBIDDEN", "409:IDEMPOTENCY_CONFLICT", "409:ADMISSION_CONFLICT", "429:ADMISSION_LIMIT_REACHED"] },
  { method: "POST", route: "/v1/archive-plan-preview", outcomes: ["success:200", "403:SCOPE_FORBIDDEN", "409:CANDIDATE_BINDING_CONFLICT"] },
  { method: "POST", route: "/v1/archive-confirmations", outcomes: ["success:201", "403:SCOPE_FORBIDDEN", "409:BASELINE_VERSION_CONFLICT", "409:ARCHIVE_AUDIT_VERSION_CONFLICT", "409:IDEMPOTENCY_CONFLICT"] },
  { method: "POST", route: "/v1/archive-anomaly-resolutions", outcomes: ["success:201", "403:SCOPE_FORBIDDEN", "409:BASELINE_VERSION_CONFLICT", "409:ARCHIVE_AUDIT_VERSION_CONFLICT", "409:IDEMPOTENCY_CONFLICT"] },
  { method: "POST", route: "/v1/archives", outcomes: ["success:201", "403:SCOPE_FORBIDDEN", "409:BASELINE_VERSION_CONFLICT", "409:ARCHIVE_AUDIT_VERSION_CONFLICT", "409:IDEMPOTENCY_CONFLICT"] },
] as const;

export const TEST_OPERATION_SUCCEEDED = {
  operation_id: "op-1", job_kind: "backend-vnext/preview", status: "SUCCEEDED", optimistic_version: 3,
  created_at: "2026-11-03T09:00:00Z", started_at: "2026-11-03T09:00:01Z", completed_at: "2026-11-03T09:00:02Z", diagnostic: null,
} satisfies Schemas["OperationResponse"];

export const TEST_OPERATION_RUNNING = {
  operation_id: "op-1", job_kind: "backend-vnext/preview", status: "RUNNING", optimistic_version: 2,
  created_at: "2026-11-03T09:00:00Z", started_at: "2026-11-03T09:00:01Z", completed_at: null, diagnostic: null,
} satisfies Schemas["OperationResponse"];

export const OPERATION_TERMINAL_RESPONSES = {
  SUCCEEDED: TEST_OPERATION_SUCCEEDED,
  FAILED: MANUAL_RECOVERY_TO_FAILED[1],
  CANCELLED: { ...OPERATION_FIELDS, operation_id: "operation-cancelled", job_kind: "backend-vnext/preview", status: "CANCELLED", completed_at: "2026-11-03T09:06:00Z" },
  SUPERSEDED: { ...OPERATION_FIELDS, operation_id: "operation-superseded", job_kind: "backend-vnext/preview", status: "SUPERSEDED", completed_at: "2026-11-03T09:07:00Z" },
} satisfies Record<string, Schemas["OperationResponse"]>;

export const TEST_WORKSPACE = {
  workspace_id: "ws-1", gateway_device_external_key: "device-1", business_project_id: "project-1", state: "OPEN",
  generation: 4, optimistic_version: 10, created_at: "2026-11-03T09:00:00Z", updated_at: "2026-11-03T09:00:00Z",
  current_preview_result_id: "preview-1",
} satisfies Schemas["WorkspaceResponse"];

export const TEST_UPLOAD_FULL = {
  upload_revision_id: "upload-1", workspace_id: "ws-1", generation: 4, input_completeness: "FULL", source_artifacts: {},
  optimistic_version: 9, created_at: "2026-11-03T09:00:00Z",
} satisfies Schemas["UploadRevisionResponse"];

export const TEST_SUBMIT_ACCEPTED = {
  submit_attempt_id: "attempt-1", operation_id: "submit-op", workspace_id: "ws-1", preview_result_id: "preview-1",
  generation: 4, state: "PREPARED",
} satisfies Schemas["SubmitAcceptedResponse"];

export function testPreviewResult(bundleDigest: string): Schemas["PreviewResultResponse"] {
  return {
    preview_result_id: "preview-1", workspace_id: "ws-1", upload_revision_id: "upload-1", generation: 4,
    operation_id: "op-1", business_baseline_node_id: "baseline-1", business_baseline_commit_id: "commit-a",
    derived_stale: false, bundle_digest: bundleDigest, identity_assessment_set_digest: "sha256:identity",
    identity_pairs: [], created_at: "2026-11-03T09:00:02Z",
  } satisfies Schemas["PreviewResultResponse"];
}

export const TEST_SUBMIT_ATTEMPT_FINALIZED = {
  submit_attempt_id: "attempt-1", workspace_id: "ws-1", upload_revision_id: "upload-1", preview_result_id: "preview-1",
  generation: 4, operation_id: "submit-op", state: "FINALIZED", business_baseline_node_id: "baseline-1",
  business_baseline_commit_id: "commit-a", canonical_business_digest: "sha256:business", created_at: "2026-11-03T09:00:02Z",
  submission_id: "submission-1",
} satisfies Schemas["SubmitAttemptResponse"];

export const TEST_SUBMISSION = {
  submission_id: "submission-1", submit_attempt_id: "attempt-1", workspace_id: "ws-1", upload_revision_id: "upload-1",
  preview_result_id: "preview-1", generation: 4, repository_id: "repo-1", based_on_baseline_node_id: "baseline-1",
  business_baseline_commit_id: "commit-a", repository_commit_id: "commit-b", canonical_business_digest: "sha256:business",
  canonicalization_manifest_digest: "sha256:manifest", created_by: "user-1", created_at: "2026-11-03T09:00:02Z",
} satisfies Schemas["SubmissionResponse"];

export const TEST_REVIEW_FACTS = {
  submission_id: "fe2a-history-ref-2", status: "PENDING", review_version: 5, updated_by: "reviewer",
  updated_at: "2026-11-03T09:00:00Z", identity_exception: false, events: [],
} satisfies Schemas["ReviewFactsResponse"];

export const TEST_REVIEW_HISTORY = {
  head: { node_id: "fe2a-history-ref-1", commit_id: "commit-baseline-1", version: 18 },
  nodes: [HISTORY_PAGE_ONE.nodes[1]], next_cursor: null,
} satisfies Schemas["HistoryListResponse"];
export const TEST_REVIEW_HISTORY_EMPTY = { ...TEST_REVIEW_HISTORY, nodes: [] } satisfies Schemas["HistoryListResponse"];
export const TEST_REVIEW_HISTORY_NO_PARENT = {
  ...TEST_REVIEW_HISTORY, nodes: [{ ...TEST_REVIEW_HISTORY.nodes[0]!, parent: null }],
} satisfies Schemas["HistoryListResponse"];

export const TEST_REVIEW_APPLIED = {
  submission_id: "submission-1", status: "APPROVED", review_version: 9,
  event: { sequence: 2, event_kind: "APPROVED", to_status: "APPROVED", actor_id: "reviewer", occurred_at: "2026-11-03T09:00:00Z" },
} satisfies Schemas["ReviewAppliedResponse"];

export const ARCHIVE_PLAN_READY = {
  head: { business_baseline_node_id: "baseline-4", business_baseline_commit_id: "commit-a", baseline_head_version: 21 },
  candidate_set_digest: "sha256:candidates", confirmation_requirements: [], anomalies: [], audit_validity: true,
  dispositions: [], workspace_releases: [], can_start: true, blockers: [],
} satisfies Schemas["PreviewArchivePlanResponse"];

export const ARCHIVE_PLAN_NEEDS_CONFIRMATION = {
  ...ARCHIVE_PLAN_READY, confirmation_requirements: ["sha256:selection-subject"],
  anomalies: [{ subject_kind: "PROJECT_IDENTITY_EXCEPTION", issue_code: "PROJECT_IDENTITY_EXCEPTION", target_submission_id: "submission-1", target_candidate_digest: "sha256:candidate", subject_digest: "sha256:anomaly" }],
  can_start: false, blockers: [], audit_validity: false,
} satisfies Schemas["PreviewArchivePlanResponse"];

export const TEST_ARCHIVE_CANDIDATES = {
  head: ARCHIVE_PLAN_READY.head, candidates: [{ submission_id: "submission-1", expected_candidate_digest: "sha256:candidate" }], candidate_set_digest: "sha256:candidates", blockers: [],
} satisfies Schemas["ArchiveCandidatesResponse"];
export const TEST_ARCHIVE_CANDIDATES_BLOCKED = {
  ...TEST_ARCHIVE_CANDIDATES, blockers: ["ARCHIVE_INTEGRITY_FAILURE"],
} satisfies Schemas["ArchiveCandidatesResponse"];

export const TEST_ARCHIVE_CONFIRM_EVENT = {
  event_id: "event-5", subject_kind: "CONFIRM_SELECTION", subject_digest: "sha256:old-selection-subject", sequence: 5,
  action: "CONFIRM", issue_code: null, actor_id: "owner", occurred_at: "2026-11-03T09:00:00Z",
} satisfies Schemas["ArchiveAuditEventResponse"];

export const TEST_ARCHIVE_ANOMALY_EVENT = {
  event_id: "event-7", subject_kind: "PROJECT_IDENTITY_EXCEPTION", subject_digest: "sha256:anomaly", sequence: 7,
  action: "ACKNOWLEDGE_IDENTITY_EXCEPTION", issue_code: "PROJECT_IDENTITY_EXCEPTION", actor_id: "owner", occurred_at: "2026-11-03T09:01:00Z",
} satisfies Schemas["ArchiveAuditEventResponse"];

export const TEST_ARCHIVE_CONFIRM_APPEND = { event_id: "event-6", sequence: 6 } satisfies Schemas["ArchiveAuditAppendResponse"];
export const TEST_ARCHIVE_RESOLUTION_APPEND = { event_id: "event-7", sequence: 7 } satisfies Schemas["ArchiveAuditAppendResponse"];

export const TEST_ARCHIVE_STARTED = {
  archive_plan_id: "plan-1", archive_result_id: "archive-1", baseline_node_id: "baseline-4", baseline_commit_id: "commit-a",
  baseline_head_version: 21, selected_submission_id: "submission-1", dispositions: [], released_workspace_ids: [],
  archived_by: "owner", archived_at: "2026-11-03T09:00:00Z",
} satisfies Schemas["ArchiveStartedResponse"];

export const TEST_ARCHIVE_RESULT = {
  archive_result_id: "archive-1", archive_plan_id: "plan-1", baseline_node_id: "baseline-4", baseline_commit_id: "commit-a",
  baseline_head_version: 21, selected_submission_id: "submission-1", selected_repository_commit_id: "commit-b",
  candidate_set_digest: "sha256:candidates", confirmation_refs: [], anomaly_resolution_refs: [], dispositions: [],
  archived_by: "owner", archived_at: "2026-11-03T09:00:00Z",
} satisfies Schemas["ArchiveResultResponse"];

export const TEST_OPERATION_ACCEPTED = {
  operation_id: "op-1", workspace_id: "ws-1", upload_revision_id: "upload-1", generation: 4, status: "QUEUED",
} satisfies Schemas["OperationAcceptedResponse"];

export const TEST_PREVIEW_RESULT_OTHER_OPERATION = {
  ...testPreviewResult("sha256:bundle"), operation_id: "other-operation",
} satisfies Schemas["PreviewResultResponse"];
export const TEST_PREVIEW_RESULT_OTHER_UPLOAD = {
  ...testPreviewResult("sha256:bundle"), upload_revision_id: "other-upload",
} satisfies Schemas["PreviewResultResponse"];

export const TEST_OPERATION_SUBMIT_SUCCEEDED = {
  ...TEST_OPERATION_SUCCEEDED, operation_id: "submit-op", job_kind: "backend-vnext/submit",
} satisfies Schemas["OperationResponse"];

export function testUploadRevision(inputCompleteness: Schemas["UploadRevisionResponse"]["input_completeness"]): Schemas["UploadRevisionResponse"] {
  return { ...TEST_UPLOAD_FULL, input_completeness: inputCompleteness } satisfies Schemas["UploadRevisionResponse"];
}

export function testHistoryCompareAcceptance(operationId: string): Schemas["HistoryCompareAcceptResponse"] {
  return { ...HISTORY_COMPARE_ACCEPT_BODY, operation_id: operationId } satisfies Schemas["HistoryCompareAcceptResponse"];
}

export function testArchiveResultWithRefs(): Schemas["ArchiveResultResponse"] {
  return {
    ...TEST_ARCHIVE_RESULT,
    confirmation_refs: [{ subject_digest: "sha256:selection-subject", sequence: 6 }],
    anomaly_resolution_refs: [{ subject_digest: "sha256:anomaly", sequence: 7 }],
  } satisfies Schemas["ArchiveResultResponse"];
}

export const TEST_HISTORY_CURSOR_FIRST = {
  head: { node_id: "baseline-2", commit_id: "commit-b", version: 9 },
  nodes: [{ ref_kind: "baseline_node", ref_id: "baseline-2", node_kind: "BASELINE_NODE", baseline_kind: "ARCHIVED_SUBMISSION", commit_id: "commit-b", created_at: "2026-11-03T09:00:00Z", parent: { ref_kind: "baseline_node", ref_id: "baseline-1" }, identity_exception: false }],
  next_cursor: "cursor/next",
} satisfies Schemas["HistoryListResponse"];

export const TEST_HISTORY_CURSOR_SECOND = {
  head: TEST_HISTORY_CURSOR_FIRST.head,
  nodes: [{ ref_kind: "submission", ref_id: "submission-1", node_kind: "SUBMISSION", commit_id: "commit-c", created_at: "2026-11-03T09:01:00Z", parent: { ref_kind: "baseline_node", ref_id: "baseline-1" }, eligibility_note: "NOT_CANDIDATE_BASE_ADVANCED", identity_exception: false, review_status: "PENDING" }],
  next_cursor: null,
} satisfies Schemas["HistoryListResponse"];

export const TEST_ARCHIVE_EVENTS_EMPTY = { events: [], next_after_sequence: null } satisfies Schemas["ArchiveAuditEventsResponse"];
export const TEST_ARCHIVE_EVENTS_WITH_CONFIRMATION = { events: [TEST_ARCHIVE_ANOMALY_EVENT], next_after_sequence: null } satisfies Schemas["ArchiveAuditEventsResponse"];

export const COMPLETE_RESPONSE_SCENARIOS = [
  { name: "CreateOrGet new workspace", method: "POST", route: "/v1/workspaces", status: 201, schema: "WorkspaceResponse", body: WORKSPACE_CREATED.body },
  { name: "CreateOrGet existing workspace", method: "POST", route: "/v1/workspaces", status: 200, schema: "WorkspaceResponse", body: WORKSPACE_ALREADY_EXISTS.body },
  { name: "History first page", method: "GET", route: "/v1/history?limit=100", status: 200, schema: "HistoryListResponse", body: HISTORY_PAGE_ONE },
  { name: "History cursor page", method: "GET", route: "/v1/history?limit=100&cursor=cursor%2Fnext", status: 200, schema: "HistoryListResponse", body: HISTORY_PAGE_TWO },
  { name: "Preview upload", method: "POST", route: "/v1/workspaces/{workspace_id}/upload-revisions", status: 201, schema: "UploadRevisionResponse", body: TEST_UPLOAD_FULL },
  { name: "Preview operation accepted", method: "POST", route: "/v1/workspaces/{workspace_id}/preview-operations", status: 202, schema: "OperationAcceptedResponse", body: TEST_OPERATION_ACCEPTED },
  { name: "Operation status", method: "GET", route: "/v1/operations/{operation_id}", status: 200, schema: "OperationResponse", body: TEST_OPERATION_SUCCEEDED },
  { name: "Operation running status", method: "GET", route: "/v1/operations/{operation_id}", status: 200, schema: "OperationResponse", body: TEST_OPERATION_RUNNING },
  { name: "Submit accepted", method: "POST", route: "/v1/workspaces/{workspace_id}/submit-attempts", status: 202, schema: "SubmitAcceptedResponse", body: TEST_SUBMIT_ACCEPTED },
  { name: "Review applied", method: "POST", route: "/v1/submissions/{submission_id}/review-events", status: 201, schema: "ReviewAppliedResponse", body: TEST_REVIEW_APPLIED },
  { name: "Review facts", method: "GET", route: "/v1/submissions/{submission_id}/review", status: 200, schema: "ReviewFactsResponse", body: REVIEW_FACTS },
  { name: "History compare accepted", method: "POST", route: "/v1/history-compares", status: 202, schema: "HistoryCompareAcceptResponse", body: HISTORY_COMPARE_ACCEPT_BODY },
  { name: "History compare idempotent replay", method: "POST", route: "/v1/history-compares", status: 200, schema: "HistoryCompareAcceptResponse", body: HISTORY_COMPARE_ACCEPT_BODY },
  { name: "History compare QUEUED", method: "GET", route: "/v1/history-compares/{operation_id}", status: 200, schema: "HistoryCompareResultResponse", body: HISTORY_COMPARE_QUEUED },
  { name: "History compare status", method: "GET", route: "/v1/history-compares/{operation_id}", status: 200, schema: "HistoryCompareResultResponse", body: HISTORY_COMPARE_RUNNING },
  { name: "History compare result", method: "GET", route: "/v1/history-compares/{operation_id}", status: 200, schema: "HistoryCompareResultResponse", body: HISTORY_COMPARE_SUCCEEDED },
  { name: "History compare failed", method: "GET", route: "/v1/history-compares/{operation_id}", status: 200, schema: "HistoryCompareResultResponse", body: HISTORY_COMPARE_FAILED },
  { name: "History compare cancelled", method: "GET", route: "/v1/history-compares/{operation_id}", status: 200, schema: "HistoryCompareResultResponse", body: HISTORY_COMPARE_CANCELLED },
  { name: "Archive plan preview", method: "POST", route: "/v1/archive-plan-preview", status: 200, schema: "PreviewArchivePlanResponse", body: ARCHIVE_PLAN_READY },
  { name: "Archive confirmation", method: "POST", route: "/v1/archive-confirmations", status: 201, schema: "ArchiveAuditAppendResponse", body: TEST_ARCHIVE_CONFIRM_APPEND },
  { name: "Archive anomaly resolution", method: "POST", route: "/v1/archive-anomaly-resolutions", status: 201, schema: "ArchiveAuditAppendResponse", body: TEST_ARCHIVE_RESOLUTION_APPEND },
  { name: "Archive started", method: "POST", route: "/v1/archives", status: 201, schema: "ArchiveStartedResponse", body: TEST_ARCHIVE_STARTED },
] as const;

export const RESPONSE_SCENARIO_STRING_SOURCE = "frontend/src/features/dev/mock-data.ts:SIMULATED_STRING_VALUES";

export function testHistoryCompareSucceeded(bundleDigest: string): Schemas["HistoryCompareResultResponse"] {
  const pair = HISTORY_COMPARE_SUCCEEDED.result?.pairs[1];
  if (!pair) throw new Error("history comparison fixture pair is missing");
  return {
    operation_id: HISTORY_COMPARE_SUCCEEDED.operation_id,
    status: "SUCCEEDED",
    diagnostic: null,
    result: { bundle_digest: bundleDigest, completed_at: "2026-11-03T09:15:00Z", input: { nodes: [pair.before_ref, pair.current_ref] }, pairs: [pair] },
  } satisfies Schemas["HistoryCompareResultResponse"];
}

export const RESPONSE_SOURCE_TABLE = "frontend/src/features/dev/mock-data.ts:SIMULATED_STRING_VALUES";
