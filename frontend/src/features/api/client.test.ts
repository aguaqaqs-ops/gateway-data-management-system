import { describe, expect, it, vi } from "vitest";
import { ApiError, createAuthenticatedFetch } from "./authenticated-fetch";
import { createGatewayApi } from "./client";

describe("authenticated OpenAPI client", () => {
  it("attaches the current bearer token and surfaces stable API errors", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "SCOPE_FORBIDDEN", message: "无权限", details: { scope: "project" } }), { status: 403, headers: { "Content-Type": "application/json" } }));
    const request = createAuthenticatedFetch({ baseUrl: "https://gateway.example/api", token: () => "session-token", fetcher });
    await expect(request("/v1/history")).rejects.toMatchObject({ name: "ApiError", status: 403, code: "SCOPE_FORBIDDEN", details: { scope: "project" } });
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get("Authorization")).toBe("Bearer session-token");
    expect(fetcher.mock.calls[0]?.[0]).toEqual(new URL("https://gateway.example/v1/history"));
  });

  it("does not keep a stale bearer token when the provider returns empty", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    const request = createAuthenticatedFetch({ baseUrl: "https://gateway.example", token: () => null, fetcher });
    await request("/healthz", { headers: { Authorization: "Bearer stale" } });
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).has("Authorization")).toBe(false);
  });

  it("sends idempotency and optimistic versions with mutation requests", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ operation_id: "op-1", workspace_id: "ws-1", upload_revision_id: "upload-1", generation: 4, status: "QUEUED" }), { status: 202, headers: { "Content-Type": "application/json" } }));
    const api = createGatewayApi({ baseUrl: "http://gateway.test", token: () => "test", fetcher });
    await api.startPreview("ws one", {
      expected_workspace_version: 9,
      upload_revision_id: "upload-1",
      generation: 4,
      expected_baseline_node_id: "baseline-2",
      expected_baseline_head_version: 7,
    }, "preview-key-1");
    expect(fetcher.mock.calls[0]?.[0]).toEqual(new URL("http://gateway.test/v1/workspaces/ws%20one/preview-operations"));
    const init = fetcher.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get("Idempotency-Key")).toBe("preview-key-1");
    expect(JSON.parse(String(init?.body))).toMatchObject({ expected_workspace_version: 9, expected_baseline_head_version: 7 });
  });

  it("keeps review operations limited to the approved action set and maps return status to rejection", async () => {
    const response = {
      submission_id: "sub-1",
      status: "RETURNED_FOR_REVISION",
      review_version: 8,
      event: { sequence: 4, event_kind: "RETURNED_FOR_REVISION", to_status: "RETURNED_FOR_REVISION", actor_id: "reviewer", occurred_at: "2026-11-02T12:00:00Z", reason: "需修改" },
    };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(response), { status: 201, headers: { "Content-Type": "application/json" } }));
    const api = createGatewayApi({ baseUrl: "http://gateway.test", token: () => null, fetcher });
    const result = await api.applyReview("sub-1", { expected_review_version: 7, action: "REJECT", reason: "需修改" }, "review-key");
    expect(result.status).toBe("REJECTED");
    expect(result.event.event_kind).toBe("REJECTED");
    expect(result.event.to_status).toBe("REJECTED");
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({ expected_review_version: 7, action: "REJECT", reason: "需修改" });
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get("Idempotency-Key")).toBe("review-key");
  });

  it("follows every History cursor page and returns the complete node list", async () => {
    const firstPage = {
      head: { node_id: "baseline-2", commit_id: "commit-b", version: 9 },
      nodes: [{ ref_kind: "baseline_node", ref_id: "baseline-2", node_kind: "BASELINE_NODE", commit_id: "commit-b", created_at: "2026-11-02T12:00:00Z", parent: { ref_kind: "baseline_node", ref_id: "baseline-1" }, identity_exception: false, review_status: null }],
      next_cursor: "cursor/next",
    };
    const secondPage = {
      head: firstPage.head,
      nodes: [{ ref_kind: "submission", ref_id: "submission-1", node_kind: "SUBMISSION", commit_id: "commit-c", created_at: "2026-11-02T12:01:00Z", parent: { ref_kind: "baseline_node", ref_id: "baseline-1" }, eligibility_note: "NOT_CANDIDATE_BASE_ADVANCED", identity_exception: false, review_status: "PENDING" }],
      next_cursor: null,
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(firstPage), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(secondPage), { status: 200, headers: { "Content-Type": "application/json" } }));
    const api = createGatewayApi({ baseUrl: "http://gateway.test", token: () => null, fetcher });

    const result = await api.listHistory();

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[0]?.[0]).toEqual(new URL("http://gateway.test/v1/history"));
    expect(fetcher.mock.calls[1]?.[0]).toEqual(new URL("http://gateway.test/v1/history?cursor=cursor%2Fnext"));
    expect(result.nodes.map((node) => node.ref_id)).toEqual(["baseline-2", "submission-1"]);
    expect(result.nodes[1]?.eligibility_note).toBe("NOT_CANDIDATE_BASE_ADVANCED");
    expect(result.next_cursor).toBeNull();
  });

  it("hashes uploaded files and builds the multipart manifest with the expected workspace version", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ upload_revision_id: "upload-2", workspace_id: "ws-1", generation: 2, input_completeness: "FULL", source_artifacts: {}, optimistic_version: 11, created_at: "2026-11-02T12:00:00Z" }), { status: 201, headers: { "Content-Type": "application/json" } }));
    const api = createGatewayApi({ baseUrl: "http://gateway.test", token: () => null, fetcher });
    const initial = new File(["initial-archive"], "initial.zip", { type: "application/zip" });
    const modified = new File(["modified-archive"], "modified.zip", { type: "application/zip" });
    for (const file of [initial, modified]) Object.defineProperty(file, "stream", { value: () => new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(new TextEncoder().encode(file.name === "initial.zip" ? "initial-archive" : "modified-archive")); controller.close(); } }) });
    await api.uploadRevision("ws-1", {
      expectedWorkspaceVersion: 10,
      inputCompleteness: "FULL",
      initial: { partName: "initial", mediaType: "application/zip", file: initial },
      modified: { partName: "modified", mediaType: "application/zip", file: modified },
      idempotencyKey: "upload-key",
    });
    const init = fetcher.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get("Idempotency-Key")).toBe("upload-key");
    expect(init?.body).toBeInstanceOf(FormData);
    const form = init?.body as FormData;
    const manifest = JSON.parse(String(form.get("manifest")));
    expect(manifest).toMatchObject({ expected_workspace_version: 10, input_completeness: "FULL", artifacts: { INITIAL: { part_name: "initial", media_type: "application/zip", size_bytes: 15 }, MODIFIED: { part_name: "modified", media_type: "application/zip", size_bytes: 16 } } });
    expect(typeof manifest.artifacts.MODIFIED.raw_sha256).toBe("string");
    expect(form.get("initial")).toBeInstanceOf(File);
    expect(form.get("modified")).toBeInstanceOf(File);
  });

  it("uses the typed API error class for non-success replies", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("not json", { status: 503 }));
    const request = createAuthenticatedFetch({ baseUrl: "http://gateway.test", token: () => null, fetcher });
    await expect(request("/readyz")).rejects.toBeInstanceOf(ApiError);
  });
});
