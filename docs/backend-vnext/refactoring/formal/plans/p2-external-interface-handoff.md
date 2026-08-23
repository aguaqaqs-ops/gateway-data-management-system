# P2 External Interface Handoff

状态：`pass`（从 S11 抽取的稳定对外接口；不是新的 gate，不改变 public semantics）

日期：2026-08-17

Owner：Backend vNext Architecture

本文是 P3 设计使用的**精简 P2 对外接口 handoff**。身份、限制、non-goals 和 reopen
来自已通过的 S11 记录与现行 contract/ADR。本文不复制字段表、状态机或错误矩阵，
也不重新验证 pytest / Dolt / Compose / W1/W2 / v8。

P4 默认入口：[P4 Active Context Index](p4-active-context-index.md)
完整过程证据：Git tag `docs/p2-p3-cleanup-pre-20260817` 中的
`docs/backend-vnext/refactoring/temporary/p2-r6-s11-final-handoff.md` 与
`docs/backend-vnext/refactoring/temporary/p2-r6-s11-lineage-inventory.json`
（已离开默认树；恢复：`git checkout docs/p2-p3-cleanup-pre-20260817 -- <path>`）。
清理：[P2–P3 Cleanup Manifest](p2-p3-cleanup-manifest.yaml)

```yaml
handoff_kind: p2_external_interface
s11_exit: pass
phase_2_complete: yes
public_contract_change: no
production_retest_required: no
p3_implementation_authorized: no
```

## 1. Sealed identity

生产身份是 S8 封印、S10 消费的干净 source SHA。文档 HEAD 与本 cleanup 的 docs-only
提交都不是 image input。

```yaml
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
container_validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_image: gateway-repository-service:p2-r6-final
service_image_local_tag: gateway-repository-service:local
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
host_runner_identity: host-runner:candidate=2ef884278b4998dde1e5fe224532c89b7a0cd73a;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
c0_freeze_documentation_head: 1420eaddaffb506d6c209862b9daeb510b7fc230
provenance_documentation_sha: bb00f9386cc4e0763040ee436c0132224d45323d
```

`c0_freeze_documentation_head` 是文档清理开始时的 HEAD，不是 `CANDIDATE_SHA`。
C2 之后的 docs-only 提交同样不是 image revision。

外部 audit root（不拷回文档树）：

```text
/root/gateway-s10-audit/p2-r6-s10-20260817T015148Z
/var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z
```

S10-9 inventory SHA-256：
`2a3f355a24207beff87090e16474ec9550e79237a352399baa73d734302a90ad`。

## 2. Supported surface

权威：[Repository Service Contract](../contracts/repository-service.md)。
Pydantic model 与激活 route 生成的 FastAPI OpenAPI 是 HTTP wire authority。
生成源：`vnext/repository_service/src/gateway_repository_service/http/openapi.py`。

已激活：

```text
POST /v1/repositories
POST /v1/repositories/{repository_id}/artifacts
POST /v1/repositories/{repository_id}/versioned/imports
GET  /v1/repositories/{repository_id}/operations/{operation_id}
GET  /v1/repositories/{repository_id}/versioned/refs/{ref_name}
GET  /v1/repositories/{repository_id}/versioned/commits/{commit_id}/catalog
GET  /v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows?table_name=...
GET  /healthz
GET  /readyz
```

运行边界（细节只在 contract）：

- production：global static bearer；`healthz` 未认证；`readyz` 无业务 bearer、须部署网络限制。
- 不提供 CallerIdentity / per-repository ACL。
- `ref_name` 仅 literal `main`；catalog/rows 绑定 caller 给出的 immutable `CommitId`。
- `{commit_id}` path 为 canonical base64url（无 padding）。
- rows 成功响应为 raw Arrow IPC stream。
- 默认 provider：Candidate A offline CLI；Candidate B `reserved_not_evaluated`。

Remote client：`gateway-repository-client`（见 P3 index §2.2）。没有 package README。
contract-owned fixture consumer 不是 production/P3 consumer。

## 3. Sealed limits

S11 封印的容量与测量上限（不是 SLO）：

```yaml
max_upload_bytes: 268435456
max_replay_sql_bytes: 209715200
w2_replay_band: 180-199 MiB
max_import_workers: 4
max_queued_imports: 64
max_concurrent_row_streams: 8
max_concurrent_uploads: 8
v8_supported_rows_max: 100000
candidate_b_status: reserved_not_evaluated
```

Wire JSON 上限由 contract 拥有（`MAX_CATALOG_JSON_BYTES` /
`MAX_OPERATION_JSON_BYTES` 等）。W0 只是 diagnostic；W1/W2 时间与 RSS、v8
scale-ratio 不是 SLO。100,000–1,000,000 rows 仅为 controlled preview。

## 4. Non-goals

来自 S11 与 contract §18，不在 P3 默认复制为实现：

- public GC / backup / restore / delete / repair
- metrics platform、RPO/RTO 保证
- 启用 Candidate B
- CurrentTableStore、standalone ref CAS、table/schema CAS
- 把文档 HEAD 当作 `CANDIDATE_SHA` 或 image revision
- 直接开始 Phase 3 实现（须先完成 P3 full design）
- 为同 euid 恶意 pathname 换名新增 broker / sidecar 安全证明（ADR 0012）

## 5. Reopen triggers

出现以下情况必须先修订 owning contract/ADR，不能借文档清理或 P3 实现顺手扩大：

- 真实 consumer 需要 CurrentTableStore、独立 ref CAS、rollback/promotion API
- 互不信任 tenant、外网直连、per-repository ACL、OIDC/mTLS
- 不可信 plugin / 独立 UID helper / 自定义安全 IPC
- object storage、resumable multipart、multi-node shared writer
- 合法数据集超过封印的 wire/capacity hard limit（须版本化）
- 改变 `/v1/` 已激活字段含义或必填性（走 `/v2/`）
- 需要把 Repository 历史 broker/evidence 机制复制到 capability

来源：[ADR 0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)、
[Repository Service Contract](../contracts/repository-service.md)、
[Implementation Stages §13.4](implementation-stages.md)、
[ADR 0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)。
不要从 decision ledger 恢复已被 ADR 0009 否定的 ACL/ResourcePolicy 设计。

## 6. Not authority

| 文件 | 角色 |
| --- | --- |
| `vnext/repository_service/README.md` | 描述 route 可用，但状态冻结在 P2-R5；S11 禁止把它当作 Phase 2 完成 authority。本计划不改 `vnext/`。 |
| `vnext/deploy/p2r1-cache/README.md` | 仍指向历史 `e78b564` / p2-r9-s2-step-e；不是当前 image。 |
| `temporary/phase-2/decision-ledger-*.md`（tag 内） | 过期访谈记录。 |
| S11 之前的阶段 execution/design 正文 | 过程；本 handoff + contract/ADR 取代其默认检索角色。 |

因 pytest 或 vnext 唯一引用而**保留在默认树**的路径：

- `docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md`
- `docs/backend-vnext/refactoring/formal/plans/p2-r5-commit-pinned-read-execution-plan.md`
- `docs/backend-vnext/refactoring/temporary/p2-r9-s2-step-e-container-gate.md`

## 7. Archive

不可变 pre-cleanup tag：`docs/p2-p3-cleanup-pre-20260817`
（tag object `93e7a492d81ae9272aaf5835277cf1a30cc3c2bd`，commit `7f2e2ddfd5567775bcc39c3a2e15801897feb845`）。
不可变 final tag：`docs/p2-p3-cleanup-final-20260817`（打在本 cleanup commit 上；
提交自身使用 `this_cleanup_commit`，literal SHA 见 annotated tag 说明）。

C4 已从默认树删除 236 条 archive 路径；C6 再移除 cleanup 过程记录。路径集合、hash、
外部 audit root 与保留责任人（Backend vNext Architecture）以
[cleanup manifest](p2-p3-cleanup-manifest.yaml) 为准。失败 attempt 与 R1 no-go 不删除，
只离开默认检索树。

过程记录恢复：

```bash
git checkout docs/p2-p3-cleanup-pre-20260817 -- \
  docs/backend-vnext/refactoring/temporary/p2-r6-s11-final-handoff.md
git show aa0c0889196a0907eb9ba454d46f792db3850233:docs/backend-vnext/refactoring/temporary/docs-lifecycle-cleanup-c5-verification-review.md
```
