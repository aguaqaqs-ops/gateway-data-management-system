# P2-R6 Operational Closure Staged Execution Plan

状态：Accepted — P2-R6-S0 design freeze complete, implementation ready

日期：2026-08-12

Owner：Backend vNext Architecture（stage boundary、final candidate与handoff）；Repository
Service Contract（wire、artifact、capacity、persistence与恢复语义）；Repository Service
（private implementation、operation evidence与container gate）

适用范围：`P2-R6 — Operational Closure`

本文件是P2-R6的权威逐阶段执行计划。公开wire、artifact、持久化和恢复语义仍由
[Repository Service Contract](../contracts/repository-service.md)拥有；总体组件与跨round
边界由[P2 Versioned Repository Implementation Design](p2-versioned-repository-implementation-design.md)
和[P2 Execution Checklist](p2-versioned-repository-execution-checklist.md)拥有；R6继承项由
[P2-R5 Commit-pinned Read Staged Execution Plan](p2-r5-commit-pinned-read-execution-plan.md)
拥有。本文只冻结private实现选择、stage顺序和evidence归属，不建立第二套contract。

## 1. S0 entry、authority与结论

```yaml
round: P2-R6-S0
expected_start_sha: 1fc69258047e416aff73e77e085fed3a76e37686
worktree_at_s0_start: clean
validated_code_sha: 7091c2c4836eebdc4cbee4424f20297b2d2f88bb
p2_r5_handoff_sha: cbc894ffda006130a53e57e8004895b93e8da74a
p2_r5_review_fix_sha: 1fc69258047e416aff73e77e085fed3a76e37686
historical_container_validated_code_sha: 901a13b92a0a92130d9afa001d8eb4273d544566
current_source_container_validated: no
production_retest_required: yes
phase_2_complete: no
authority_conflicts: []
design_blockers: []
r6_stage_plan_frozen: yes
s1_ready_after_s0_documentation_commit: yes
```

S0只完成独立只读审计、设计冻结和执行计划，不运行pytest、Dolt、Docker、Compose、远端
builder或v8 formal，不修改`vnext/**`。入口SHA同时包含R5 validated code、S7 handoff和
handoff review fix；两个required ancestor检查通过。历史container SHA不能证明当前source。

按authority顺序复核Repository contract §§12、14–18、P2 design §§18–21、execution
checklist §§1–2、8–10、R5 final handoff/§§8.1–10、Phase 2 delivery plan的R6/exit边界，
以及Service README、Dockerfile、Compose、image build/digest helper、retained cache和P2-R1
v8 launcher。没有发现会改变public contract或阻断S1的冲突。

## 2. Audited implementation inventory

以下是S0对production consumer、状态存储、线程/进程生命周期和既有测试的实际审计结果，
不是把R5 handoff当作代码事实转抄。

### 2.1 Artifact lifecycle与admission

- import success先持久化`SUCCEEDED` result和consumed binding，再best-effort删除private ref和
  artifact bytes；清理失败只记录日志，不改变commit或operation结果。startup recovery已能
  重试`SUCCEEDED` residual。
- `artifact_ttl_seconds=24h`存在于settings，但当前没有ordinary failed/orphan定时清理器；
  ordinary failed bytes会保留。store已经能列出artifact references、判断protected引用并记录
  bytes删除时间。
- `ADMISSION_PENDING`、`QUEUED`、`RUNNING`及带`MANUAL_RECOVERY_REQUIRED`错误的FAILED引用
  被视为protected。Artifact admission pin使用`flock`保护ready package，清理不能绕过它。
- upload在分配PENDING前检查repository、声明大小和磁盘，但没有共享upload并发permit。
  import submission在durable effect前检查ready package、disk admission和queue；queue full为
  429，service/disk unavailable为503。
- 磁盘reserve实现为`max(5 GiB, 10% volume)`；import额外保留默认1 GiB headroom。当前默认
  4 import workers、64 queue；每repository reservation和execution lock已提供single writer。

### 2.2 Dispatcher、marker与verification

- 当前恰好一个dispatcher。`_try_claim_one()`在单dispatcher下先检查process-local in-flight，
  再durable claim并递增；它不是多dispatcher原子容量协议，因此R6保持single dispatcher并把
  该约束变为显式不变量和回归证据。
- dispatcher最长约100 ms醒一次，idle时约10 Hz查询queued candidates；候选仓库还会扫描
  FAILED history并解析`error_json`寻找manual barrier。`Condition.notify_all()`没有sticky
  generation，通知可能丢失并由下一次poll补偿。
- `inspect_marker()`先读取全部branch heads，再为每个branch分别查询Dolt log；query count随
  branch数量线性增长。`CandidateAImportProvider._refs_for_commit()`没有consumer。
- FULL_SCAN逐表调用stream；每表重新使用`import_timeout_seconds=3600`，没有覆盖catalog和
  全部table的whole-operation deadline。read/replay已有取消基础设施，但verification没有把
  cumulative deadline和cancel/reap贯穿整个scan。

### 2.3 Read stream、cleanup与operations

- Arrow bridge在慢consumer下对每次取队列使用`asyncio.to_thread(..., timeout=0.05)`，持续占用
  default executor调度；这就是Phase 2 exit blocker `R5-CLEANUP-02`。
- catalog memo最多4项，但provider按HTTP request创建，当前没有cross-request命中。没有测量前
  不引入process-wide cache。
- Arrow测试存在process-global `ClassVar` hooks；Candidate A stream上层取消后最终`close()`
  没有稳定传递`cancelled=true`；另有无consumer helper、忽略参数和局部冗余分支。
- private manual-recovery admin CLI要求Service停止并取得root lock。当前没有production
  whole-root snapshot/restore helper、runbook或restored Compose lifecycle evidence。
- request ID middleware已存在；日志字段和格式不统一，尚不能稳定关联operation、duration、
  bytes、result和cleanup outcome。R6只补最小structured diagnostics，不建metrics platform。

### 2.4 Container、external evidence与provenance

- R4 deferred nodeid已存在：
  `tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay`。
  两个R5 Remote Client Compose nodeid当前不存在，只能在后续stage创建和收集。
- 当前Compose不发布Service host port；inside-network client应使用attached one-shot client
  container，gate-host client在Linux gate host使用validated container bridge address。
- 当前build-context helper摘要实际复制进image的Repository source输入，而target launcher以
  整个`git archive HEAD`计算source tree；S0在clean entry上得到不同摘要，因此当前协议不能
  证明`image_matches_build_context=true`。entry HEAD的helper结果为
  `sha256:07f39261eeefee9dad38a974b959e734d592673274d92a4f2b653ffd0c4564ca`，whole-archive
  结果为`sha256:280d525ec408e477792040c09438bc3d2dc273c91119c1e60d9a60a551a7cf42`；
  `tree_match=no`。R6必须统一口径，不能通过修改证据文本掩盖差异。
- W1尚未以R6正式external dataset descriptor提供；near-200 MB W2尚未生成。S0环境可发现
  Docker和Dolt命令，但未运行；target launcher和审计输出目录在当前S0 host不存在，远程
  builder/cache readiness也未形成当前证据。

## 3. Scope、defaults与explicit non-goals

### 3.1 Frozen operational defaults

| Setting | Environment | Default | Reload boundary |
| --- | --- | ---: | --- |
| ordinary failed/orphan TTL | `GATEWAY_REPOSITORY_ARTIFACT_TTL_SECONDS` | `86400` | container recreate |
| cleanup fallback interval | `GATEWAY_REPOSITORY_ARTIFACT_CLEANUP_INTERVAL_SECONDS` | `300` | container recreate |
| concurrent uploads | `GATEWAY_REPOSITORY_MAX_CONCURRENT_UPLOADS` | `8` | container recreate |
| import workers | `GATEWAY_REPOSITORY_MAX_IMPORT_WORKERS` | `4` | container recreate |
| queued imports | `GATEWAY_REPOSITORY_MAX_QUEUED_IMPORTS` | `64` | container recreate |
| concurrent row streams | `GATEWAY_REPOSITORY_MAX_CONCURRENT_ROW_STREAMS` | `8` | container recreate |
| FULL_SCAN cumulative timeout | `GATEWAY_REPOSITORY_FULL_SCAN_TIMEOUT_SECONDS` | `3600` | container recreate |
| fixed disk reserve | `GATEWAY_REPOSITORY_MIN_FREE_DISK_BYTES` | `5368709120` | container recreate |
| fractional disk reserve | `GATEWAY_REPOSITORY_MIN_FREE_DISK_FRACTION` | `0.10` | container recreate |
| import headroom | `GATEWAY_REPOSITORY_IMPORT_HEADROOM_BYTES` | `1073741824` | container recreate |

Settings在process启动时一次性解析和校验。部署方用受控env file给Compose插值，Compose只
显式透传已声明的`GATEWAY_REPOSITORY_*`键；修改值后使用`up --no-build --force-recreate`，
不能用`docker restart`假装刷新container environment。不建设YAML配置系统或hot reload。
代码、validator、依赖、Dockerfile或build input变化仍需新image和新candidate。

### 3.2 In scope

- artifact cleanup scheduler、retention、upload/read admission和runtime ownership；
- single-dispatcher sticky wake、durable manual barrier query和marker bounded lookup；
- FULL_SCAN cumulative deadline、cancel/cleanup和slow Arrow stream closure；
- private whole-root snapshot hold/check及operator runbook；
- structured logs、W1/W2 capacity report、final Compose/full/v8 gates；
- build、跨host transfer、image identity和candidate provenance协议。

### 3.3 Explicit non-goals

- public GC、artifact retention、backup、restore、delete或repair API；
- generic scheduler、ResourcePolicy、per-caller quota、accounting或metrics platform；
- multi-dispatcher、多ASGI process、multi-node writer或shared writable root；
- online/per-repository snapshot、RPO/RTO、CommitId disaster-stability；
- process-wide catalog cache、Candidate B activation或P3 design/implementation。

## 4. Frozen implementation decisions

### 4.1 Artifact cleaner与upload admission

`ServiceRuntime`拥有一个non-daemon cleaner。startup reconciliation完成后立即sweep一次；
artifact lifecycle变化触发sticky wake，300秒只作为漏通知/外部时间推进的fallback。shutdown
先停止和join cleaner，再关闭control DB并释放durable-root lock。

删除顺序固定为：枚举Service-owned exact UUID/staging shape；取得artifact admission pin；用
durable references复核eligible；unlink/确认已不存在；记录bytes-deleted timestamp。未知、
畸形或无法证明owner的path只记录脱敏诊断，不删除。成功结果持久化后继续即时删除并由cleaner
重试residual；ordinary FAILED从`completed_at`起24小时，unreferenced orphan从artifact
`created_at`起24小时。PENDING/QUEUED/RUNNING/manual FAILED无限期保留到状态改变。

upload permit在创建PENDING、打开staging文件或读取request body前non-blocking取得；满载返回
429，所有正常、异常和disconnect路径释放。replay不重新占upload permit，仍受import worker、
single writer和disk admission约束。import继续在durable effect前执行queue和disk admission。

### 4.2 Dispatcher与manual barrier

保持一个dispatcher。新增durable`manual_recovery_required`布尔列，所有FAILED transition和
manual correction在同一transaction更新该列与error/status；migration对旧FAILED行一次性
按现有typed error回填。candidate query使用indexed `NOT EXISTS`排除具有manual barrier的
repository，不按history长度解析JSON。

runtime notification带单调generation：enqueue、recovery、manual correction后的启动、worker
完成、capacity release和shutdown均递增并通知；waiter在同一lock内比较generation，防止
lost wake。DB仍是真相，startup必查一次。不得以扩大poll interval换取通过，也不增加第二个
dispatcher。回归必须证明无idle周期查询、通知与wait竞态不丢任务、无double claim、global
worker bound和per-repository FIFO/mutex保持。

### 4.3 Marker与FULL_SCAN

marker benchmark使用1、8、32、128个normal branches，并加入MANUAL/private refs；每档warm-up
后运行5次，记录query count、duration、process count和zero/unique/ambiguous/parent/ref语义。
目标为single query；若固定Dolt版本无法一次返回全部证据，允许最多2次bounded query，但query
和process count必须与branch数无关。128-branch p95门槛为
`max(500 ms, 3 * one-branch p95)`；不满足则不得以process-wide cache隐藏问题。

新增`full_scan_timeout_seconds=3600`，monotonic deadline从verification进入时开始，覆盖catalog
和所有table。每次provider call使用`min(existing per-call timeout, remaining deadline)`；
remaining耗尽即设置cancellation并TERM/KILL/wait/reap owned child。若可证明main未发布，结果为
普通`VERIFICATION_FAILED_NOT_PUBLISHED`并清理private state；发布证据不确定时仍走既有manual
recovery，不因timeout降低保守性。

### 4.4 Read stream与Post-R5 cleanup

Arrow bridge改为event-driven thread-to-event-loop handoff，禁止每batch/每50 ms调用default
executor polling。row-stream permit默认8，在发送response headers前取得；第9路返回503，permit
持有到worker、reader、query temp和child process全部清理完成。测量1/4/8路slow consumers及
第9路拒绝，记录default executor pending/running、thread/process/temp peak和cleanup duration。

```yaml
post_r5_cleanup_disposition:
  R5-CLEANUP-01:
    decision: measure_then_close_without_process_wide_cache_by_default
    acceptance: W1_W2_and_1_4_8_stream_measurement_recorded
    reopen: only_if_catalog_process_cost_dominates_and_bounded_invalidation_is_designed
  R5-CLEANUP-02:
    decision: replace_to_thread_polling_with_event_driven_bridge
    phase_2_exit_blocker: yes
    acceptance: default_executor_pressure_bounded_and_zero_residual
  R5-CLEANUP-03:
    decision: remain_closed
    evidence: tests/test_import_shutdown.py::test_runtime_shutdown_propagates_bridge_shutdown_error_after_releasing_resources
  R5-CLEANUP-04:
    decision: replace_process_global_ClassVar_hooks_with_instance_scoped_test_probe
  R5-CLEANUP-05:
    decision: propagate_effective_cancellation_to_ProcessStream_close_and_CommandResult
  R5-CLEANUP-06:
    decision: exact_rg_then_delete_confirmed_dead_helpers_noop_arguments_and_redundant_branches
```

`R5-CLEANUP-04/05/06`必须close，不以“harmless”静默延期；删除前把exact symbol和全部consumer
搜索保存在stage report。`R5-CLEANUP-03`不重开。

### 4.5 Structured diagnostics

每个适用event至少记录`event`、`request_id`、opaque `repository_id`、`operation_id`、
`artifact_id`、`stage`、`duration_ms`、`size_bytes`、`result`/stable `code`和cleanup outcome；
不存在的字段省略而不是写假值。禁止token、raw idempotency key、raw row、SQL、provider stderr、
host/internal path和private ref。日志不改变public response或建立新audit state machine。

### 4.6 Private snapshot/restore

新增private operator `snapshot hold`/`snapshot check`，不注册HTTP route。`hold`要求Service已停止，
取得durable-root exclusive lock，完成SQLite WAL checkpoint并确认无open writer，输出machine-
readable ready evidence后保持lock直到operator结束helper；外部设施在此窗口snapshot整个data
root。`check`要求Service仍停止，在空目标root完成whole-root restore后检查layout、SQLite
integrity、artifact/control binding和Dolt repository可读性。随后以相同支持版本启动、通过
ready/integrity和expected public facts。禁止overlay restore、只恢复SQLite或单个Dolt tree。

### 4.7 W1/W2与result record

W1是10–100 MB external read-only脱敏真实package，不复制进Git或普通CI。descriptor由dataset
owner提供`dataset_id`、`revision`、package SHA/size、producer、classification、schema/rows、
expected public facts和批准的保留/访问位置。结果只记录安全descriptor、candidate/image
identity、settings、timing、resource peaks、result code和cleanup，不记录raw payload。

W2使用固定generator版本和seed，`synthetic=true`，按W1的schema、row width、NULL、key/index
和value distribution生成；以192 MiB replay SQL作为初始安全目标并记录实际compressed package
size。若实际package没有达到formal的near-200 MB边界，generator必须调整可重复数据而不能把
小package伪称为通过。W2只证明boundary/resource safety，不替代W1业务代表性。

### 4.8 Candidate、image与provenance

最终image记录三个分离字段：literal clean `CANDIDATE_SHA`；最近一次触碰Dockerfile实际复制/
构建输入的`build_input_revision`；由唯一helper计算的effective `source_tree_sha256`。Docker
labels、build harness和target launcher必须调用同一helper/manifest；不得一端hash effective
inputs、另一端hash整个Git archive。remote/local image ID和三个label均须相等。

candidate commit不自引用SHA。clean后把字面量`CANDIDATE_SHA`写入外部gate record；remote在
独立detached worktree检出exact SHA。gate期间不得amend/rebase/squash。任一build-input变化产生
新candidate并使旧image/evidence superseded。final provenance/handoff commit只允许修改已验证
effective digest之外的formal docs；分别记录`validated_code_sha`、
`container_validated_code_sha`和`provenance_documentation_sha`。

## 5. External prerequisite preflight

```yaml
r6_final_gate_ready: no
blocking_external_prerequisites:
  - id: R6-EXT-W1
    state: not_provided_to_s0
    required: dataset_descriptor_and_read_only_package_access
    owner: business_dataset_owner
    latest_required_stage: P2-R6-S6
  - id: R6-EXT-BUILDER
    state: current_readiness_not_proven
    required: designated_remote_builder_and_retained_dependency_cache
    owner: release_operator
    latest_required_stage: P2-R6-S10
  - id: R6-EXT-GATE-HOST
    state: target_launcher_and_output_directory_not_present_on_s0_host
    required: launcher_gate_host_output_permissions_and_image_transfer_path
    owner: release_operator
    latest_required_stage: P2-R6-S10
early_implementation_blocked: no
phase_2_exit_blocked_until_resolved: yes
```

S1至S5不因外部资源缺失而伪造或等待；进入S6 W1 evidence和S10 final gate前必须把对应state
改为真实`ready`并保存取得方式。未满足时保持`production_retest_required=yes`、
`phase_2_complete=no`。

## 6. Green stages

### P2-R6-S0 — Design freeze and inventory

```yaml
goal: freeze audited operational decisions, stages, evidence and failure boundaries
allowed_paths:
  - docs/backend-vnext/refactoring/formal/README.md
  - docs/backend-vnext/refactoring/formal/plans/p2-r6-operational-closure-execution-plan.md
  - docs/backend-vnext/refactoring/formal/plans/p2-versioned-repository-execution-checklist.md
  - docs/backend-vnext/refactoring/formal/plans/p2-versioned-repository-implementation-design.md
  - docs/backend-vnext/refactoring/formal/plans/phase-2-implementation-design-and-delivery-plan.md
explicit_non_goals: production, test, Docker, Compose, dependency, dataset or runtime changes
implementation_decisions: sections 3 through 5 are frozen before S1
tests_and_markers: none; formal docs-only
directed_gate: markdown links and anchors, five old-reference searches, git diff --check
container_trigger: no
failure_boundary: any authority conflict makes S0 no-go without production edits
expected_commit: "docs(repository): add P2-R6 operational closure execution plan"
exit: clean committed documentation, complete inventory, no blocker, s1_ready=yes
next_stage_ready: P2-R6-S1 from the clean S0 documentation commit
```

### P2-R6-S1 — Operational configuration and runtime ownership

```yaml
goal: add startup-only settings, upload/read permits, cleaner ownership and structured diagnostics
allowed_paths: Repository Service settings/runtime/capacity/logging, Service README, Compose env wiring, focused tests
explicit_non_goals: artifact deletion policy implementation, generic policy/quota/metrics, hot reload
implementation_decisions: explicit env allowlist; nonblocking pre-effect permits; runtime-owned stop/join order
tests_and_markers: unit; timing/thread lifecycle cases additionally serial
directed_gate: defaults, overrides, invalid combinations, pre-effect 429/503, permit leak and shutdown tests
container_trigger: final image superseded; Compose rendering gate now, final production gate at S10
failure_boundary: invalid settings fail startup; permit cannot survive request/runtime cleanup
expected_commit: "feat(repository): add operational configuration and diagnostics"
exit: effective redacted settings observable and all runtime components have deterministic owners
next_stage_ready: P2-R6-S2
```

### P2-R6-S2 — Artifact retention, admission and lifecycle

```yaml
goal: implement success residual retry, ordinary TTL, orphan cleanup and upload admission
allowed_paths: upload artifact, import store/recovery, control DB migration, runtime cleaner, focused tests
explicit_non_goals: public GC/delete/retention API and deletion of versioned history/control metadata
implementation_decisions: startup plus event plus 300s sweep; exact paths; admission pin; protected-state query
tests_and_markers: unit; real Dolt lifecycle integration; clock/thread/process timing additionally serial
directed_gate: success, cleanup failure retry, ordinary TTL, orphan, PENDING/QUEUED/RUNNING/manual, restart
container_trigger: source image superseded; restored/container lifecycle collected in S7/S10
failure_boundary: uncertain ownership/reference or cleanup error retains bytes and never changes durable result
expected_commit: "feat(repository): close artifact retention and admission"
exit: Contract section 12 and artifact portion of section 17 have direct evidence
next_stage_ready: P2-R6-S3
```

### P2-R6-S3 — Marker, dispatcher, deadlines and Post-R5 cleanup

```yaml
goal: remove branch-linear marker work, idle polling/JSON scans, unbounded FULL_SCAN and slow-stream polling
allowed_paths: import provider/store/worker/verification, read bridge/process, DB migration, focused tests
explicit_non_goals: multi-dispatcher, process-wide cache, changed marker/public error semantics
implementation_decisions: bounded marker queries; durable barrier; sticky generation; cumulative deadline; event bridge
tests_and_markers: unit/integration; concurrency, timeout, stream and process cleanup additionally serial with -n 0
directed_gate: 1/8/32/128 branches, idle/candidate queries, lost wake, 1/4/8 slow streams, cancel/reap
container_trigger: source image superseded; affected process smoke before exit, final container gate at S10
failure_boundary: ambiguity stays manual; timeout cannot publish; disconnect cannot leak worker/child/temp
expected_commit: "fix(repository): close import and stream operational backlog"
exit: R5-CLEANUP-01/02/04/05/06 dispositions closed and 03 remains closed
next_stage_ready: P2-R6-S4
```

### P2-R6-S4 — Private snapshot/restore and restored lifecycle

```yaml
goal: implement operator-only snapshot hold/check and whole-root restore verification
allowed_paths: private admin tooling, root locking/control DB adapters, runbook, focused tests
explicit_non_goals: public route, online or per-repository snapshot, RPO/RTO and cross-version guarantee
implementation_decisions: stopped service, exclusive lock, WAL checkpoint, whole root, empty restore target
tests_and_markers: real Dolt integration plus serial; no hand-written Dolt skipif
directed_gate: fresh root, import/read, snapshot, mutate, restore, integrity/ready/public facts
container_trigger: yes; helper and restored volume must run in target container boundary
failure_boundary: failed hold/check keeps service stopped and never overlays a live root
expected_commit: "feat(repository): add private snapshot recovery tooling"
exit: quiescent snapshot/restore repeatable with zero provider/process/thread/temp residual
next_stage_ready: P2-R6-S5
```

### P2-R6-S5 — Build-context and image provenance

```yaml
goal: unify candidate, build-input and effective-source provenance across build and launcher
allowed_paths: Dockerfile, build/digest scripts, target launcher, Compose build harness, README and tests
explicit_non_goals: whole-repository content digest and self-referential candidate commit
implementation_decisions: one effective-input manifest/helper and three independent identity fields
tests_and_markers: unit build-context/harness tests; directed image build smoke
directed_gate: docs-only, source, lock, Dockerfile, dirty tree, stale label and remote/local identity cases
container_trigger: yes; Docker/build boundary changes require current-stage image evidence
failure_boundary: any label/digest/image mismatch is no-go and old evidence is superseded
expected_commit: "fix(repository): unify repository image provenance"
exit: builder and launcher recompute identical values from exact clean candidate
next_stage_ready: P2-R6-S6 after external W1 descriptor is ready
```

### P2-R6-S6 — W1/W2 and capacity evidence

```yaml
goal: record representative and boundary capacity, concurrency, cleanup and resource peaks
allowed_paths: deterministic synthetic generator, evidence harness/tests, safe result schema, capacity runbook
explicit_non_goals: commit W1/raw rows/secrets or claim W2 business representativeness
implementation_decisions: external read-only W1; deterministic same-shape W2; 1/4/8 concurrency matrices
tests_and_markers: integration and serial where real Dolt, time budgets, streams or subprocesses are used
directed_gate: W1 10-100 MB, near-200 MB W2, marker, FULL_SCAN, upload/import/read, disk/headroom
container_trigger: provisional production image capacity run; final selected evidence repeated at S10
failure_boundary: missing descriptor or unsafe result record prevents stage exit without falsifying ready/pass
expected_commit: "test(repository): add P2-R6 capacity evidence gates"
exit: W1/W2 facts, settings, timings, peaks, outcomes and known limitations are complete
next_stage_ready: P2-R6-S7
```

### P2-R6-S7 — Compose harness and lifecycle inventory

```yaml
goal: add and run R4 replay, R5 inside/gate-host client, fresh/restart/restored Compose gates
allowed_paths: Compose, container harness/tests, deploy and Service README
explicit_non_goals: publish production host port or make Service depend on Client
implementation_decisions: one-shot attached client container; gate-host bridge address; exact nodeids
tests_and_markers: container/integration/serial as required; all three exact inventory nodeids collected
directed_gate: import restart/replay, pinned read inside network/from gate host, fresh/restart/restored
container_trigger: yes
failure_boundary: any skipped/missing nodeid or container/network/volume/process/thread/temp residual fails exit
expected_commit: "test(repository): add P2-R6 Compose lifecycle gates"
exit: deferred inventory is real, collected and green on the current provisional candidate
next_stage_ready: P2-R6-S8
```

### P2-R6-S8 — Full regression and candidate preparation

```yaml
goal: close affected package gates, classifications, static checks and all review findings
allowed_paths: owning production/test/docs scope needed to fix observed failures
explicit_non_goals: accepted-ignore, broad marker exclusion or harmless-flake waiver
implementation_decisions: exact consumer rg before deletion; shared parameters for isomorphic malformed cases
tests_and_markers: three Repository packages plus fixture consumer; five-package ruff/mypy; unit/integration/serial
directed_gate: parked-Dolt unit classification, S6 transient worker nodeid, old-reference searches, leak audit
container_trigger: any build/deploy change reruns its directed gate; final image waits for sealed S9 SHA
failure_boundary: first failure is fixed in owning scope and affected gates rerun; no partial pass language
expected_commit: "test(repository): close Phase 2 operational regression"
exit: clean green source tree with no open implementation/review finding
next_stage_ready: P2-R6-S9
```

### P2-R6-S9 — Final candidate seal

```yaml
goal: freeze the exact source candidate and literal CANDIDATE_SHA without self-reference
allowed_paths: none after clean candidate selection; external gate record only
explicit_non_goals: amend, rebase, squash, provenance doc edit or image reuse after build-input change
implementation_decisions: detached remote worktree; immutable candidate; separate validated SHA fields
tests_and_markers: run ./vnext/scripts/run-tests.sh with no --ignore before remote build
directed_gate: git status clean, five old-reference searches, full command/count report
container_trigger: yes; this exact SHA owns the final image
failure_boundary: any source/test/build-input change invalidates seal and returns to the owning stage
expected_commit: none; S8 clean HEAD becomes literal CANDIDATE_SHA
exit: exact clean SHA and effective build inputs recorded outside candidate
next_stage_ready: P2-R6-S10 when builder/cache/gate-host prerequisites are ready
```

### P2-R6-S10 — Exact-candidate production gate

```yaml
goal: build, transfer and validate the exact candidate through full, Compose, W1/W2 and v8 gates
allowed_paths: no candidate writes; audit output and ephemeral remote/gate-host resources only
explicit_non_goals: substitute earlier image/evidence, change canonical v8 parameters or defer a final gate
implementation_decisions: retained cache build, auditable save/load, identity check, fresh/restart/restored
tests_and_markers: no-ignore run-tests, three Compose nodeids, W1/W2, Candidate A 66-record v8 runs=5
directed_gate: section 8 protocol and canonical commands
container_trigger: final mandatory
failure_boundary: any mismatch/failure keeps production_retest_required=yes and phase_2_complete=no
expected_commit: none; evidence-only against immutable CANDIDATE_SHA
exit: all R5 14-item input inventory and runtime resource cleanup are closed
next_stage_ready: P2-R6-S11
```

### P2-R6-S11 — Build-context-external provenance and Phase 2 handoff

```yaml
goal: record immutable evidence, SHA lineage, limitations and Phase 2 exit decision
allowed_paths: formal provenance/handoff docs outside the verified effective source digest
explicit_non_goals: production, tests, Dockerfile, Compose, build scripts or any candidate build input
implementation_decisions: validated_code_sha, container_validated_code_sha and documentation SHA remain separate
tests_and_markers: no test rerun for docs-only commit; markdown links, old-reference classification, diff check
directed_gate: verify docs-only diff is outside digest and worktree is clean after commit
container_trigger: no
failure_boundary: evidence gap records no-go; documentation cannot turn a failed/missing gate into pass
expected_commit: "docs(repository): record P2-R6 and Phase 2 handoff"
exit: P2-R1 through R6 SHAs, image provenance, capacity limits and phase_2_complete are explicit
next_stage_ready: Phase 3 full design only when phase_2_complete=yes
```

## 7. Requirement-to-evidence matrix

`existing`表示S0已确认nodeid存在但本轮未执行；`planned`表示后续stage必须创建后再收集，不能
在S0称为pass。优先扩展共享fixture/参数表，不为仅payload或错误文本差异复制测试函数。

| Requirement | Evidence / nodeid / command | State | Owning stage |
| --- | --- | --- | --- |
| Contract §17 full regression | Repository contracts/service/client与fixture consumer四命令；`./vnext/scripts/run-tests.sh`无`--ignore` | existing command | S8–S10 |
| success cleanup failure不改结果 | `tests/test_import_worker.py::test_success_cleanup_failure_does_not_change_result` | existing | S2 |
| succeeded residual startup cleanup | `tests/test_import_recovery.py::test_succeeded_residual_cleanup_on_reconcile` | existing | S2 |
| ordinary failed TTL/orphan TTL | `tests/test_artifact_cleanup.py::test_ordinary_failed_artifact_expires`；`tests/test_artifact_cleanup.py::test_orphan_artifact_expires` | planned | S2 |
| RUNNING/manual/PENDING/QUEUED retention | existing `tests/test_import_operation_store.py::test_artifact_references_mark_protected_states`、`tests/test_import_recovery.py::test_manual_failed_retained_after_reconcile` plus planned cleaner clock cases | mixed | S2 |
| exact protected deletion decision | `tests/test_import_operation_store.py::test_can_delete_artifact_bytes_requires_no_protected_references` | existing | S2 |
| upload concurrency/fail-before-effect | `tests/test_upload_concurrency.py::test_ninth_upload_is_rejected_before_pending_and_body` | planned | S1–S2 |
| import global bound/per-repository writer/FIFO | `tests/test_import_worker.py::test_cross_repository_respects_global_worker_bound`、`tests/test_import_worker.py::test_same_repository_running_mutex_observed`、`tests/test_import_worker.py::test_same_repository_fifo_completion_order` | existing | S3 |
| queue admission/double claim | `tests/test_import_operation_store.py::test_admit_new_import_rejects_when_queue_full`、`tests/test_import_worker.py::test_dispatcher_does_not_double_claim_same_repository` | existing | S3 |
| disk reserve + import headroom | `tests/test_upload_artifact_admission.py`、`tests/test_capacity.py` equality/below/fraction cases | existing | S2/S6 |
| marker branch growth and exact semantics | `tests/test_import_marker_capacity.py::test_marker_query_count_is_branch_independent` plus 1/8/32/128 report | planned | S3/S6 |
| idle/candidate barrier pressure | `tests/test_import_worker.py::test_dispatcher_idle_does_not_poll`；`tests/test_import_worker.py::test_notification_generation_prevents_lost_wakeup` | planned | S3 |
| single dispatcher atomic boundary | existing double-claim/global-bound/mutex tests plus explicit runtime invariant test | mixed | S3 |
| whole-operation deadline | `tests/test_import_worker.py::test_full_scan_deadline_is_cumulative`；`tests/test_import_worker.py::test_full_scan_timeout_cancels_and_reaps` | planned | S3 |
| slow streams/default executor pressure | existing Arrow bridge backpressure/cancel/join tests plus planned `test_slow_streams_do_not_poll_default_executor` | mixed | S3/S6 |
| row stream cap/cleanup | planned 1/4/8 and ninth-pre-header-503 tests; existing HTTP disconnect/concurrent stream integration | mixed | S3/S6 |
| R5-CLEANUP-01 | W1/W2 catalog process/query/memory measurement and explicit no-process-cache disposition | planned | S3/S6 |
| R5-CLEANUP-02 | event-driven bridge pressure test; zero default-executor polling/residual | planned; exit blocker | S3/S6 |
| R5-CLEANUP-03 | `tests/test_import_shutdown.py::test_runtime_shutdown_propagates_bridge_shutdown_error_after_releasing_resources` | existing closed | preserve |
| R5-CLEANUP-04 | instance-scoped probe isolation/concurrent bridge tests | planned | S3 |
| R5-CLEANUP-05 | cancellation observed as `CommandResult.cancelled=true` after disconnect/shutdown | planned | S3 |
| R5-CLEANUP-06 | saved exact `rg` consumers before deletion plus affected unit/integration tests | planned | S3/S8 |
| quiescent whole-root snapshot/restore | `tests/test_snapshot_admin.py::test_hold_checkpoints_and_holds_root_lock`；`tests/test_snapshot_admin.py::test_whole_root_restore_preserves_public_facts` | planned integration+serial | S4/S7 |
| W1 representative evidence | external descriptor + public HTTP/client import/read facts + timing/resource/result record | external planned | S6/S10 |
| W2 near-200 MB boundary | deterministic generator replay + `synthetic=true` record + timing/resource/cleanup | planned | S6/S10 |
| build provenance | existing `test_build_context_digest.py`/`test_compose_build_harness.py` extended for unified three-field protocol | mixed | S5 |
| R4 restart/replay | `tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay` | existing deferred, not run S0 | S7/S10 |
| R5 inside-network Remote Client | `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network` | planned, absent S0 | S7/S10 |
| R5 gate-host Remote Client | `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host` | planned, absent S0 | S7/S10 |
| fresh/restart/restored lifecycle | Compose lifecycle harness including S4 snapshot restore | planned | S7/S10 |
| Candidate A 66-record v8 | section 8 canonical launcher command, `--v8-formal --runs 5` | external planned | S10 |
| zero residual | explicit process/thread/temp/container/network/volume inventory in each directed report and final gate | mixed | S2–S10 |

R5 14项input归属：1和13归S8/S9；2–3归S5/S10；4–7归S7/S10；8归S10；9–10归
S6/S10；11归S3/S6；12归S7/S10；14仅S10全绿后关闭。任一项不得从handoff静默删除。

## 8. Final candidate and production gate protocol

S9在clean source上执行且不得保留R5临时ignore：

```bash
./vnext/scripts/run-tests.sh
```

container inventory必须逐项收集：

```text
tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
```

S10使用clean detached checkout、retained dependency cache和
`gateway-repository-service:p2-r6-final`构建production image，记录build command、candidate、
build-input revision、effective source digest和remote image ID；以`docker save | load`或等价
可审计流程传至gate host，验证remote/local image ID和labels。之后运行no-ignore full gate、
R4/R5 Compose、fresh/restart/restored、W1/W2和资源清理。

Canonical v8 command必须原样执行，不自行改写formal参数：

```bash
sudo env \
  GATEWAY_P2R1_REPO_ROOT=<clean-final-source-checkout> \
  GATEWAY_P2R1_IMAGE=gateway-repository-service:p2-r6-final \
  GATEWAY_P2R1_CACHE_CONDITION=retained-dependency-cache \
  /usr/local/libexec/gateway-p2r1-target-launcher.sh \
  --output /var/lib/gateway/repository/audit-rerun/<unique-r6-run>/p2-r1.jsonl \
  --v8-formal \
  --runs 5
```

通过条件同时包括：`image_matches_build_context=true`、66-record五轮完整、W1/W2、全部
Compose nodeids、no-ignore full gate以及container/network/volume/process/thread/temp零残留。
否则保持Phase 2 no-go。

## 9. Mandatory old-reference classification

S0已对整个repository执行checklist §9的五组精确`rg`并人工分类：

1. verification level搜索：current authority和production使用`FULL_SCAN`；ADR 0008和temporary
   historical材料中的旧`FULL`/manifest术语属于明确superseded历史；checklist命令有self-hit。
2. effect-state搜索：current formal命中是删除/禁止旧模型的否定说明；operations/glossary的
   同名单词属于其他application capability；temporary phase-0材料是历史。
3. CAS/store搜索：current formal命中均为non-goal、reopen或future Current说明，没有激活
   `StoreKind`、table/schema CAS或generic store。
4. path/version搜索：production命中是private变量、内部test或明确拒绝；current docs其余命中
   是backend benchmark/internal path或negative compatibility说明，没有旧public path。
5. wire/readback搜索：除checklist命令self-hit外只命中temporary historical phase-0材料；current
   Repository wire没有旧JSON/gRPC或before/after readback状态。

Historical/superseded ADR保留，不为清空搜索破坏历史。每个后续stage按影响scope重跑；S8/S9
再次对全repository执行并保存分类。删除symbol/path前另存exact consumer搜索。

## 10. S0 handoff

```yaml
round: P2-R6-S0
start_sha: 1fc69258047e416aff73e77e085fed3a76e37686
status: pass
r5_handoff_consumed: yes
validated_code_sha: 7091c2c4836eebdc4cbee4424f20297b2d2f88bb
current_source_container_validated: no
authority_conflicts: []
design_blockers: []
r6_stage_plan_frozen: yes
r6_evidence_matrix_complete: yes
post_r5_cleanup_inventory_complete: yes
r5_cleanup_02_exit_plan_frozen: yes
w1_input_ready: no
w2_generation_plan_frozen: yes
remote_builder_ready: no
target_launcher_ready: no
r6_final_gate_ready: no
candidate_provenance_protocol_frozen: yes
container_gate_inventory_complete: yes
production_retest_required: yes
phase_2_complete: no
container_trigger: no
container_gate_run: no
s1_ready: yes
```

S0 documentation commit完成后成为S1的clean entry SHA；它不在自身内容中写入自引用SHA。
完整commit SHA和`worktree_clean`由S0最终报告记录。外部W1/builder/launcher状态只阻塞S6/S10
及最终exit，不阻塞S1 operational implementation。
