# P2-R6-S7 Compose Lifecycle Execution Plan

状态：Ready for independent design review

日期：2026-08-16

关联设计：[P2-R6-S7 Compose Lifecycle Design](p2-r6-s7-compose-lifecycle-design.md)
上游 handoff：[P2-R6-EXT-W1 Stage K Final Handoff](../../temporary/p2-r6-ext-w1-stage-k-final-handoff.md)
总计划：[P2-R6 Operational Closure Execution Plan](p2-r6-operational-closure-execution-plan.md)

本文把 formal S7 拆成可控上下文的会话步骤。任务提示词只用于启动一个已冻结步骤，不替代
本文的 allowed paths、验收条件、审核边界或上游 Contract。任何步骤发现 production/build
input 变化、Contract 冲突、容器身份不一致或缺失外部前置，必须停止并回到 owning step。

## 0. Frozen entry and global rules

```yaml
branch: phase1/gate-ownership-repair
entry_commit: 0b4969fe
entry_head_full_sha: 0b4969fe04ab3d133c297a474bac1ecc27111336
stage_k_exit: pass
R6-EXT-W1: yes
P2-R6-S6_ready: yes
production_source_identity_from_stage_j: 656a66bf04714cce987c85649246c3767b2586e2
stage_j_image_id: sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
package_version: v1
public_contract_change: no
nodeid_count: 4
phase_2_complete: no
```

`entry_commit` 在执行会话开始时必须用 `git rev-parse HEAD` 取得完整 40 字符 SHA；本文
使用短 SHA 仅作可读标签。每个新会话都重新检查 branch、HEAD、worktree 和上一步 handoff，
不假定上次会话状态。

### 0.1 Session policy

- **同一会话保留上下文**：同一 implementation step 内的局部代码、focused tests、静态检查、
  文档记录和该 step commit；不得跨越独立审核、Compose image rebuild 或 gate conclusion。
- **建议新开对话**：设计审核、跨 Compose/deployment boundary、真实 Docker gate、snapshot
  lifecycle、独立 review、发现 blocker 后重新审核，以及从一个实现提交进入下一个 owning
  boundary。
- **只读审核步骤**：审核者只读检查实际 diff、evidence 和结果，不顺手修改生产/测试代码，
  发现问题后回到指定实现步骤。
- **测试分类**：纯 parser/oracle/runner parsing 为 unit；真实 Dolt、subprocess、uvicorn、
  Docker 或落盘 lifecycle 为 integration；涉及 timeout、signal、join、stream、cleanup 的
  测试必须 serial，并使用 `-n 0`。
- **容器规则**：任何 Dockerfile、Compose、container harness、client image 或运行时接线变化
  都触发当前 candidate rebuild；旧 image 只能记录为 ancestor evidence。
- **失败边界**：不在 review/handoff 步骤修复；不把 skip、旧 image、host-only smoke 或
  incomplete cleanup 写成 PASS。

## 1. Step map

| step | name | session | implementation/review | output | next |
| --- | --- | --- | --- | --- | --- |
| S7-0 | Entry reconciliation | new | read-only + preflight | entry record | S7-1 |
| S7-1 | Independent design review | new | read-only | design review record | S7-2 or return to design |
| S7-2 | Compose/client harness | new after review; same session through focused gates | implementation | harness commit + focused evidence | S7-3 |
| S7-3 | Remote consumer nodeids | same as S7-2 | implementation/test | client/nodeid commit + focused evidence | S7-4 |
| S7-4 | Harness implementation review | new | read-only | review record | S7-5 or return to S7-2/3 |
| S7-5 | Provisional image/preflight | new | container boundary | image identity + preflight evidence | S7-6 |
| S7-6 | R4 restart/replay gate | same as S7-5 | directed Docker gate | per-node evidence | S7-7 |
| S7-7 | R5 inside/gate-host gates | same as S7-5 | directed Docker gate | two per-node evidence records | S7-8 |
| S7-8 | Restored lifecycle implementation | new | implementation/integration | lifecycle test commit + focused evidence | S7-9 |
| S7-9 | Restored lifecycle gate | same as S7-8 if image unchanged; otherwise new image session | directed Docker gate | lifecycle evidence | S7-10 |
| S7-10 | Independent lifecycle review | new | read-only | review record | S7-11 or return to S7-8/9 |
| S7-11 | Final S7 candidate/container gate | new | rebuild + all four nodeids | final S7 evidence/handoff | S8 |

The split deliberately keeps implementation context small while grouping the two remote-client
nodeids in one test boundary. S7-5 and S7-11 are separate image events: S7-5 is a provisional image
for directed gates; S7-11 is the exact final S7 candidate after all implementation/review fixes.

## 2. S7-0 — Entry reconciliation

**Session:** New conversation from the Stage K commit. Read-only; no production/test edits.

**Read first:** `AGENTS.md`, this plan §§0–2, design §§1–9, Stage K handoff, operational plan S7,
Testing Conventions, S4 snapshot guide, README Compose/client sections.

**Checks:**

- verify branch `phase1/gate-ownership-repair`, complete HEAD, clean worktree;
- verify Stage K, S6 capacity/W2/concurrency and Stage J provenance are ancestors/consistent;
- verify four target nodeids: the existing R4 nodeid and the three versioned-read/lifecycle nodeids;
- verify `repository_client/tests/fixtures/versioned_v1` and expected oracle files are present;
- verify Docker, Compose, remote builder/cache, gate-host bridge and secret-file prerequisites are
  discoverable without running a production gate;
- verify S4 `snapshot_admin hold/check` focused/integration tests are available and no source change
  has silently altered restore semantics.

**Do not:** add tests, create image, run full Compose lifecycle, or claim S7 ready.

**Evidence:** `p2-r6-s7-step-0-entry-reconciliation.md`, containing start SHA, worktree state,
nodeid inventory, environment preflight, unresolved external prerequisite list and exact image
identity fields.

**Exit:** identity and oracle are locatable; no design or environment blocker. If Docker/builder/
bridge is unavailable, record `S7_entry_ready: no` and stop; do not substitute host-only proof.

**Prompt:** `复核 S7 入口 SHA、四个 nodeid、fixture oracle 和容器前置，生成 entry record。`

## 3. S7-1 — Independent design review

**Session:** New conversation after S7-0. Read-only; no implementation edits.

**Review questions:**

- Does the design preserve public Contract, S4 restore semantics and the no-host-port topology?
- Is the fourth lifecycle nodeid the sole owner of fresh/restart/restored facts?
- Are c0/c1/c2, catalog, rows, main movement and mutation-absence facts sufficient and deterministic?
- Are `force-recreate` restart, fresh volume and restored volume semantics unambiguous?
- Is the ephemeral client boundary test-only and absent from production Compose dependencies?
- Does every failure path include process/thread/Dolt/query-temp/container/network/volume cleanup?
- Are image/client/source/provenance fields sufficient to prevent old-image substitution?
- Are S7/S10 ownership boundaries explicit, with no Phase 2 completion claim?

**Output:** independent review record with `review_status: pass|fail`, reviewed design SHA, findings,
and `allow_s7_implementation: yes|no`.

**Exit:** no blocker. A failure returns to the design document; the reviewer does not patch it.

**Prompt:** `只读审核 S7 设计、nodeid ownership、lifecycle 语义与容器边界，提交 design review。`

## 4. S7-2 — Compose/client harness implementation

**Session:** New conversation after S7-1 pass; same session may continue through S7-3 focused gates.

**Allowed scope:** Compose/test harness support, repository service integration test support,
  temporary client runner/image definition, test-only README instructions. No public route,
  production Service dependency, Contract or snapshot semantic change.

**Implementation:**

- add deterministic project/volume/token naming and `finally` cleanup;
- render `p2-r2` Compose config and assert no Service host port or resident client service;
- add dynamic service-network and Linux bridge discovery with explicit evidence fields;
- build/run ephemeral client from same candidate using locked `repository_client` project and
  `versioned_v1` fixtures; keep fixture material read-only;
- add typed client summary parsing and secret/path redaction assertions;
- add Docker object inventory helpers that never delete outside the generated project/volume set;
- add focused negative probes for missing readiness, wrong token, wrong network and non-empty restore
  target where existing harness boundaries support them.

**Verification:** harness unit tests, Compose config/static tests, repository_client focused unit,
  repository_service focused unit; `ruff`/`mypy` for touched packages; `git diff --check`.

**Allowed commit:** `test(repository): add S7 compose lifecycle harness`.

**Exit:** no production contract or permanent deployment topology change; focused gates green;
  no external Docker gate claim yet.

**Prompt:** `实现 S7 Compose/client harness 和资源 inventory，完成 focused gates 并提交。`

## 5. S7-3 — Remote consumer nodeids

**Session:** Continue S7-2 session while context and worktree remain bounded.

**Implementation:**

- create `tests/test_versioned_read_compose_e2e.py`;
- implement exact inside-network and gate-host nodeids using the existing consumer, not a second
  oracle or direct database access;
- implement exact `test_compose_repository_service_fresh_restart_restored_lifecycle` nodeid;
- keep each nodeid independent with unique project/volume/token and per-node cleanup;
- assert c0/c1/c2, pinned c1/c2 catalog/rows, main=c2, restart durability and post-snapshot mutation
  absence according to the design matrix;
- mark real Docker/subprocess/timeout tests `integration` and `serial` as required;
- update README/deferred inventory only after exact paths and semantics exist.

**Verification before image:**

```bash
cd vnext/repository_service
uv run pytest -m unit tests/test_compose_build_harness.py tests/test_versioned_read_http.py
uv run pytest -m 'integration and serial' -n 0 \
  tests/test_snapshot_admin.py::test_whole_root_restore_preserves_public_facts
cd ../repository_client
uv run pytest -m unit tests/test_versioned_fixture_consumer.py
```

Also run touched-package ruff/mypy and `git diff --check`. These are not the S7 Compose PASS.

**Allowed commit:** `test(repository): add S7 remote consumer lifecycle nodeids`.

**Exit:** four exact nodeids collect; markers are valid; test oracle and cleanup owners are unique;
  no broad marker exclusion; implementation review is ready.

**Prompt:** `补齐四个精确 S7 nodeid 与 versioned_v1 oracle，完成 focused/marker 检查并提交。`

## 6. S7-4 — Harness implementation review

**Session:** New conversation; read-only.

**Review:**

- inspect only S7-2/S7-3 actual diff and test ownership;
- verify no host port, persistent client, Docker socket, host-root mount or secret leakage;
- verify client image/source lock identity and no production dependency addition;
- verify all fixed-time tests are serial and pure logic tests do not create Dolt;
- verify the fourth nodeid owns restore facts and no duplicate owner exists;
- verify cleanup is bounded on success, expected failure and signal/timeout;
- verify exact nodeids and README inventory match the formal design.

**Output:** `p2-r6-s7-step-4-harness-review.md` with reviewed commits, findings and
`allow_provisional_image: yes|no`.

**Exit:** zero blocker findings. Findings return to S7-2 or S7-3; do not start Docker gate with an
open review.

**Prompt:** `只读审核 S7 harness、client boundary、markers、cleanup 和 nodeid ownership。`

## 7. S7-5 — Provisional image and preflight

**Session:** New conversation after harness review pass; container boundary.

**Tasks:**

- record clean source HEAD and effective build inputs;
- build the provisional Service image with retained dependency cache using the formal build script;
- build/resolve the ephemeral client runner from the same candidate and record its identity;
- verify image labels, image ID, local/remote transfer if used, Docker Compose config and no public port;
- provision a temporary bearer secret with service UID/GID and mode checks;
- perform only health/readiness and client-network reachability preflight; do not call S7 PASS.

**Evidence:** image identity, client identity, Compose rendered config, bridge discovery, secret
permission result, project/resource inventory baseline.

**Exit:** exact provisional image/client identity matches source; config boundary is correct; no
resource residue. Any Dockerfile/dependency/Compose change after this step invalidates the image.

**Prompt:** `构建当前 S7 provisional image/client runner，核对 provenance、Compose config 和网络前置。`

## 8. S7-6 — R4 import restart/replay gate

**Session:** Continue S7-5 gate session; no source edits.

**Nodeid:** `test_compose_repository_service_import_restart_replay`.

**Required observations:**

- create/upload/import through HTTP with the provisional image;
- capture operation, artifact, expected commit and main/ref facts before restart;
- stop/recreate the Service with the same named volume;
- wait for ready, poll/replay operation state, resolve main and verify no duplicate commit/publication;
- verify private refs, query temps, Dolt children and temporary roots drain;
- execute `down -v --remove-orphans` and assert project-scoped containers/networks/volumes are zero.

**Evidence:** command, nodeid, candidate/image identity, status transitions, commit/ref facts,
cleanup inventory, elapsed/resource summary and stderr classification.

**Exit:** existing R4 nodeid passes on the provisional image. A failure returns to the owning test
or S7-5 image step; do not alter acceptance semantics to fit the result.

**Prompt:** `在 provisional image 上运行 R4 import restart/replay nodeid，记录状态与零残留。`

## 9. S7-7 — R5 inside-network and gate-host gates

**Session:** Continue S7-6 session if no image/source change; otherwise start a new image session.

**Nodeids:**

```text
test_compose_remote_client_commit_pinned_read_inside_network
test_compose_remote_client_commit_pinned_read_from_gate_host
```

**Required observations for each:**

- run the same consumer and fixture oracle through its assigned network boundary;
- verify c1/c2 catalog and row facts by immutable CommitId;
- verify main resolves c2 while c1 remains readable;
- move/reconfirm main after pinned-read setup where the harness supports the branch movement;
- assert auth/readiness, Arrow media/termination and exact consumer summary;
- capture network path, service endpoint form, image/client identity and cleanup inventory;
- prove no host port was published and no client container remains.

**Exit:** both nodeids pass independently. A failure returns to S7-3 or S7-5; no aggregate partial
pass is allowed.

**Prompt:** `运行 inside-network 与 gate-host pinned-read nodeid，逐项记录 public facts 和 cleanup。`

## 10. S7-8 — Restored lifecycle implementation

**Session:** New conversation after S7-7 because snapshot/restore is a separate container/root
  ownership boundary.

**Allowed scope:** the fourth Compose lifecycle nodeid, snapshot volume/archive harness, runbook,
  and minimum test-only support. Reuse S4 `snapshot_admin`; do not modify its production semantics.

**Implementation:**

- implement fresh project/volume setup and capture c0/c1/c2 public facts;
- stop Service and run `hold`, require complete ready JSON while helper remains alive;
- copy the entire named volume once; stop hold with controlled signal and assert exit 0;
- create a new empty restore volume and prove it is empty before copying;
- restore the entire root, fix ownership, run `check` while Service is stopped;
- start the same provisional image against restored volume and replay public facts;
- create a post-snapshot mutation in the source run and assert it is absent in restored facts;
- reject/record partial, SQLite-only, single-Dolt and non-empty overlay procedures where the harness
  exposes those directed cases;
- assert all process/thread/query-temp/container/network/volume cleanup on both success and failure.

**Verification:** focused snapshot harness tests, real Dolt integration/serial tests, lifecycle
nodeid collection tests, touched-package ruff/mypy, `git diff --check`.

**Allowed commit:** `test(repository): add S7 restored lifecycle gate`.

**Exit:** lifecycle nodeid is implemented and focused gates are green; no final S7 PASS yet.

**Prompt:** `实现 S7 fresh/restart/restored lifecycle nodeid，复用 S4 hold/check 并完成 focused gates。`

## 11. S7-9 — Restored lifecycle gate

**Session:** Continue S7-8 only if no image/build input changed; otherwise new provisional-image
  session and repeat S7-5 preflight.

**Nodeid:** `test_compose_repository_service_fresh_restart_restored_lifecycle`.

**Gate:** run the complete design lifecycle matrix, capture snapshot/restore JSON, public facts at
snapshot and restore, post-snapshot mutation absence, same-image readiness, and full resource
inventory. Do not replace public HTTP facts with direct SQLite/Dolt inspection.

**Exit:** lifecycle nodeid passes with zero residuals. A failure returns to S7-8 or S7-5 based on
whether the cause is harness behavior or image/provenance.

**Prompt:** `运行 restored lifecycle nodeid，验证 snapshot facts、mutation isolation 和 zero residual。`

## 12. S7-10 — Independent lifecycle review

**Session:** New conversation; read-only.

**Review questions:**

- Were all four exact nodeids run on the same provisional candidate?
- Does restart mean force-recreate with the same volume, and is restored target independently empty?
- Does `hold` precede whole-root copy and does `check` precede restored Service startup?
- Are c0/c1/c2 and post-snapshot mutation facts public and reproducible?
- Are inside-network and gate-host paths genuinely different and host-port-free?
- Are process/thread/Dolt/query-temp/container/network/volume inventories zero per nodeid?
- Do image/client labels, source digest, lock identity and candidate SHA agree?
- Are S7/S10 deferred items explicit and not silently dropped?

**Output:** `p2-r6-s7-step-10-lifecycle-review.md` with reviewed commit range, nodeid result table,
findings, residual risk and `allow_final_s7_gate: yes|no`.

**Exit:** zero blocker findings. Any finding returns to S7-8/9 or the earlier harness owner.

**Prompt:** `只读审核四个 S7 nodeid、restore ordering、public oracle、provenance 和 zero residual。`

## 13. S7-11 — Final S7 candidate/container gate and handoff

**Session:** New conversation after lifecycle review pass. This is the final S7 candidate boundary.

**Tasks:**

- start from the clean source commit after all S7 fixes and record literal candidate SHA;
- run full required source checks appropriate to touched packages and the exact S7 Compose nodeids;
- rebuild the current candidate Service image and ephemeral client runner; transfer/verify image IDs
  if using a remote builder;
- rerun all four nodeids without broad ignore or substitution;
- record command/count/status, source/build/image/client identities, network/volume/project names,
  public facts, timing/resource summaries and zero residual inventory;
- update the S7 handoff and operational index; do not modify production code during handoff;
- explicitly carry S7/S10 deferred gates and `phase_2_complete: no`.

**Container decision:**

```text
Current HEAD: <literal S7 final candidate SHA>
Container rebuild required: yes
Reason: S7 Compose/client/lifecycle boundary changed
Last verified image revision: <same candidate>
Last verified source-tree/image id: <source digest> / <image id>
Container gate for current candidate: passed | no-go
Deferred gates/nodeids: S8/S9/S10 exact inventory as applicable
Required execution point: S7 final candidate
```

**Exit:** all four nodeids pass on the exact current candidate, independent reviews pass, resource
cleanup is zero, and handoff says `S7_exit: pass`, `S8_ready: yes`, `phase_2_complete: no`.
Any candidate/build/input change after this step invalidates the seal and returns to S7-2, S7-8 or
S7-11 as appropriate.

**Prompt:** `重建当前 S7 final candidate，运行四个 Compose nodeid，收集 provenance/cleanup 并形成 handoff。`

## 14. Handoff schema

The final S7 handoff must include at least:

```yaml
stage: P2-R6-S7
stage_status: pass | no-go
entry_sha: <stage-k descendant>
validated_code_sha: <exact S7 candidate>
container_validated_code_sha: <exact S7 candidate>
service_image_id: sha256:<64 hex>
client_image_id: sha256:<64 hex or host-runner identity>
source_tree_sha256: sha256:<64 hex>
service_uv_lock_sha256: <64 hex>
client_uv_lock_sha256: <64 hex>
nodeids:
  import_restart_replay: pass | fail | missing
  pinned_read_inside_network: pass | fail | missing
  pinned_read_gate_host: pass | fail | missing
  fresh_restart_restored: pass | fail | missing
all_nodeids_current_candidate: yes | no
public_oracle: versioned_v1.c0_c1_c2
snapshot_semantics: S4 whole-root hold/check
zero_process_thread_query_temp_residual: yes | no
zero_container_network_volume_residual: yes | no
independent_harness_review: pass | fail
independent_lifecycle_review: pass | fail
S7_exit: pass | no-go
S8_ready: yes | no
production_retest_required: yes
phase_2_complete: no
deferred_scope:
  - S8 full regression/candidate preparation
  - S9 exact candidate seal
  - S10 final production/v8/container gate
```

## 15. Reopen and rollback rules

- A failed test/harness assertion returns to its owning implementation step; preserve the failed
  evidence and add a repair record rather than rewriting it.
- A source/Compose/Dockerfile/dependency/client-image change invalidates all later image evidence;
  rebuild from the repaired candidate and rerun affected nodeids.
- A Contract/topology/restore semantic change stops S7 and requires a design review update before
  implementation resumes.
- A missing builder, bridge or secret prerequisite is an entry no-go, not a reason to substitute
  host-only or old-image evidence.
- A docs-only handoff commit does not change `container_validated_code_sha`; record documentation
  SHA separately.

## 16. Plan verdict

```yaml
plan_status: ready_for_independent_design_review
steps: 12
implementation_sessions: 4
independent_review_steps: 3
container_boundary_steps: 3
exact_compose_nodeids: 4
same_session_grouping_explicit: yes
task_prompts_intentionally_minimal: yes
phase_2_complete: no
next: S7-0 Entry reconciliation
```
