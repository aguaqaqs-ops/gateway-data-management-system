# P2-R6-S3 Staged Execution Guide

状态：Temporary execution coordinator — implementation pending

日期：2026-08-14

适用：`P2-R6-S3 — Marker, dispatcher, deadlines and Post-R5 cleanup`

本文件只把P2-R6正式计划中的S3拆成五个可串行执行、独立提交和独立handoff的实现批次，
并给出整体评审与最终候选container gate的执行顺序。它不拥有public wire、持久化、恢复、
容量或部署语义，也不建立第二套S3 exit标准。正式owner、当前仓库事实和上一批次已提交的
handoff优先于本文；出现冲突时必须停止执行并回到正式owner，不得用本文覆盖authority。

## 1. Authority与必读顺序

每个批次开始前至少读取本文的全局规则、当前批次和上一批次handoff，并按以下顺序处理
authority：

1. 仓库根目录`AGENTS.md`；
2. [Repository Service Contract §§10–11、13–14、17–18](../../formal/contracts/repository-service.md)；
3. [P2-R6 Operational Closure Staged Execution Plan §§3–5、S3、§§7、9–10](../../formal/plans/p2-r6-operational-closure-execution-plan.md)；
4. [P2 Versioned Repository Implementation Design §§14–16、18–21](../../formal/plans/p2-versioned-repository-implementation-design.md)；
5. [P2 Versioned Repository Execution Checklist §§1–2、8–10](../../formal/plans/p2-versioned-repository-execution-checklist.md)；
6. [P2-R5 Commit-pinned Read Staged Execution Plan §§4.1–4.4、8.1、9–10](../../formal/plans/p2-r5-commit-pinned-read-execution-plan.md)；
7. [Testing Conventions](../../../testing-conventions.md)与
   [Proportional Assurance Policy](../../formal/policies/proportional-assurance-and-risk-based-verification-policy.md)；
8. [ADR 0012](../../formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)；
9. [P2-R9-S2 Step E container gate provenance](../p2-r9-s2-step-e-container-gate.md)。

正式计划冻结S3目标、non-goals和exit；本文只拥有批次顺序、checkout纪律、focused gate和
handoff格式。普通类名、私有helper拆分、测试fixture组织和日志措辞由实现者按现有代码风格
保守选择。

## 2. Entry snapshot与计划文档提交

本文编写前的已确认入口：

```yaml
branch: phase1/gate-ownership-repair
planning_base_sha: 76b07460ba2ddc7de085d537cc1a8afb185882aa
s2_validated_code_sha: e78b564a112b2a040740e3e07d7e6f04329d06e9
s2_provenance_documentation_sha: 76b07460ba2ddc7de085d537cc1a8afb185882aa
s2_image_id: sha256:87e4e908bfa63370033256b380c6582c39fb6888749131633d5e856ae649a007
s2_source_tree_sha256: sha256:2cc377e74be2ab342ee09028ce54ff77a4690c5a5f12ce633959bfe6643172a2
s2_container_gate: passed
s3_entry_ready: yes
phase_2_complete: no
production_retest_required: yes
```

本文及索引必须先形成独立docs-only clean commit。S3-A不得直接把业务代码混在未提交的计划
文档之上。S3-A执行者记录包含该文档提交的实际`start_sha`，确认`planning_base_sha`和
`s2_validated_code_sha`都是ancestor，并重新计算effective source digest，证明计划提交没有
改变Repository Service image build inputs。

若实际HEAD、ancestor、worktree或digest不符，停止并报告；不得reset、checkout或覆盖用户
已有修改。S2 image只证明`e78b564`，第一处S3 production变更后立即成为ancestor evidence，
不得表述为当前HEAD已通过container gate。

## 3. S3目标、范围与non-goals

### 3.1 Stage outcome

S3必须同时完成：

- marker lookup的Dolt query/process count不随normal branch数量增长；
- dispatcher无idle polling、无逐repository FAILED history JSON scan、无lost wakeup；
- FULL_SCAN使用覆盖catalog和全部table的cumulative monotonic deadline；
- slow Arrow stream使用event-driven thread-to-event-loop handoff，不持续轮询default executor；
- `R5-CLEANUP-01/02/04/05/06`的S3 implementation disposition关闭，`03`保持closed；
- marker、CAS、public errors、Arrow wire、recovery保守性和runtime resource ownership不回归。

### 3.2 Explicit non-goals

所有批次共同禁止：

- multi-dispatcher、多ASGI process、multi-node/shared writable root或通用scheduler；
- process-wide catalog cache、generic metrics/quota/accounting platform；
- public DTO、route、error code、Arrow envelope/checkpoint/digest或marker语义变化；
- Candidate B activation、新production dependency或无当前consumer的通用abstraction；
- S4 snapshot/restore、S6 W1/W2、S7 Compose client harness、S9/S10 final production/v8 gate；
- 恢复S2 broker/helper/socket、双UID、sidecar proof、tombstone budget或同euid恶意pathname模型；
- 用大量private interleaving探针替代Contract行为测试；
- 在一个批次中顺带开始后续批次。

`R5-CLEANUP-01`在S3关闭的是实现处置：继续使用request/session-scoped bounded memo并明确
不引入process-wide cache。W1/W2和完整容量接受证据仍由S6拥有；S3不得等待外部W1，也不得
宣称S6 evidence已经通过。handoff固定写为：

```yaml
R5-CLEANUP-01:
  implementation_disposition: closed_no_process_wide_cache
  capacity_evidence: deferred_to_P2-R6-S6
```

## 4. Cross-batch invariants

1. 五个批次严格串行。每批从上一批clean green commit开始，完成commit和handoff后停止。
2. S3-A的migration、barrier写入和dispatcher query必须同批交付，不能留下读写语义不一致的
   中间schema。
3. S3-B先稳定marker provider边界；S3-C随后在同一provider/CLI上增加deadline，避免并行修改
   `versioned_import/provider.py`和`candidate_a/dolt_cli.py`。
4. S3-D的event handoff、instance probe、effective cancellation和permit/resource release必须
   同批交付，不能留下只改消费端或只改producer的生命周期中间态。
5. DB仍是dispatcher真相；single dispatcher、global worker bound、per-repository FIFO/mutex、
   no-double-claim不得改变。
6. Marker ambiguity、publication uncertainty和malformed durable evidence继续fail closed；timeout
   只有在main可证明未发布时才是普通`VERIFICATION_FAILED_NOT_PUBLISHED`。
7. FULL_SCAN deadline从verification入口开始，不能按table重置；NONE/STRUCTURAL既有语义不变。
8. Arrow正常结束才输出EOS；provider/conversion/cancel失败保持truncated stream，不追加JSON。
9. Row-stream permit持有到bridge worker、reader、child和query temp全部清理完成。
10. 测试按业务行为命名；每个不变量只有一个权威owner。删除production机制时同步删除只服务
    于该机制的mock、fixture、probe和重复测试。
11. 真实Dolt或落盘process测试标`integration`；固定Event/thread/subprocess相对时间预算的测试
    标`serial`并以`-n 0`运行；不手写Dolt `skipif`。
12. 每批保存删除symbol前的exact consumer `rg`；每批按受影响scope运行old-reference搜索，
    S3-E对全repository汇总人工分类。
13. 中间批次不重建image；每份handoff必须明确当前image gate为`deferred`或`stale`，last
    verified image仍绑定`e78b564`。只有全部finding关闭后的S3 code candidate执行一次Step E。
14. 不amend上一批提交。用于Step E的candidate封板后不得amend/rebase/squash。

## 5. Delivery sequence与conversation protocol

```text
docs-only execution baseline
  -> S3-A durable barrier and dispatcher wake
  -> S3-B bounded marker inspection
  -> S3-C cumulative FULL_SCAN deadline
  -> S3-D event-driven Arrow lifecycle
  -> S3-E Post-R5 residue and source closure
  -> fresh independent S3 review and finding closure
  -> exact-candidate Step E and provenance
  -> P2-R6-S4 handoff
```

| Batch | Outcome | Suggested commit |
| --- | --- | --- |
| S3-A | v16 durable manual barrier、indexed candidate query、sticky generation、zero idle polling | `fix(repository): persist manual import barriers and wake dispatcher` |
| S3-B | branch-independent marker query/process、exact semantics、capacity report、dead helper removal | `fix(repository): bound marker inspection across branches` |
| S3-C | catalog+all-table cumulative deadline、cancel/reap、normal/recovery一致 | `fix(repository): enforce cumulative full scan deadlines` |
| S3-D | event-driven Arrow bridge、instance probes、effective cancellation、slow-stream cleanup | `fix(repository): replace arrow polling with event-driven handoff` |
| S3-E | no-cache disposition、dead residue、cross-batch regression、source candidate preparation | `refactor(repository): close post-r5 operational residue` |

推荐每批使用一个新对话；不得并行。新对话只接收本文、上一批完整handoff和当前批次prompt。
批次中途不得因上下文长度切换；只有在focused gate通过、提交完成、worktree clean并输出handoff
之后才能切换。整体review和Step E分别使用新的干净对话，降低实现者确认偏差，并把immutable
candidate操作与代码修改隔离。

若减少对话数量，最多允许A+B同一对话、D+E同一对话，但仍须保留独立commit/handoff/stop
boundary；C、整体review和Step E保持独立。无论对话如何组合，本文的五个batch boundary不变。

## 6. S3-A — Durable manual barrier and dispatcher wake

### Objective

把manual recovery barrier从FAILED `error_json` projection提升为同transaction维护的durable
布尔事实，并用sticky generation替代dispatcher idle polling，同时保持single-dispatcher、FIFO、
mutex和capacity语义。

### Allowed scope

- `control_db.py`的最小forward migration与admin schema verification；
- `versioned_import/store.py`的FAILED transitions、manual correction和candidate query；
- `versioned_import/worker.py`的single dispatcher notification/wait；
- runtime/submission/recovery中已有worker notification wiring；
- focused migration/store/worker/runtime tests与共享test support。

不得修改marker SQL、FULL_SCAN provider API、Arrow bridge或public wire。

### Required work

1. 将control DB从v15向前迁移到v16，为`repository_import_operations`增加
   `manual_recovery_required INTEGER NOT NULL`及0/1约束，并增加匹配实际candidate/barrier
   query shape的索引。
2. 对旧FAILED行按typed error一次性回填：exact manual code为true，合法ordinary terminal
   error为false。missing、malformed或矛盾FAILED evidence不得静默回填false；沿用control DB
   invariant的fail-closed启动失败语义，并用migration test冻结。
3. 非FAILED行必须为false。所有mark-failed、manual correction和FAILED/SUCCEEDED correction
   必须在更新status/error/result的同一transaction中同步该列。
4. `admit_new_import`和dispatcher candidate选择使用durable列；candidate query以indexed
   `NOT EXISTS`或等价单次query排除barrier repository，不再逐candidate调用
   `has_unresolved_manual_barrier()`或解析全部FAILED history。
5. public stored error、operation projection、recovery audit和artifact protection保持既有语义；
   durable bool不进入public DTO。
6. `ImportWorkerPool`在Condition lock内维护monotonic notification generation。wait协议必须在
   DB检查前取得generation snapshot，并在同一lock下比较，覆盖query与wait之间的通知竞态。
7. startup必查DB一次；enqueue、recovery完成、worker completion/capacity release和shutdown等
   实际state变化递增generation并notify。idle无候选时不得按100 ms或其他固定间隔查询。
8. storage error可有bounded error retry/backoff，但不能退回idle polling或busy loop。
9. 保持恰好一个dispatcher，不建设multi-dispatcher原子capacity协议。

### Required evidence

- fresh v16、v15→v16、current reopen、newer rejection、migration rollback；
- manual/ordinary backfill、malformed FAILED fail-closed、non-FAILED false；
- mark-failed与两类manual correction同transaction更新；
- indexed candidate query不解析JSON、不dispatch barrier repository；
- `test_dispatcher_idle_does_not_poll`；
- `test_notification_generation_prevents_lost_wakeup`；
- explicit single-dispatcher runtime invariant；
- 既有double-claim、global bound、per-repository FIFO/mutex、storage glitch tests；
- focused ruff/mypy、pytest和`git diff --check`。

只为固定线程时间预算的测试加`serial`；纯migration/query shape测试不得创建真实Dolt HOME。

### Prompt S3-A

```text
你在 /root/gateway-data-management-system 仓库执行P2-R6-S3-A。

开始前完整读取p2-r6-s3-staged-execution-guide.md的§§1–6、正式S3 owner和上一轮S2 Step E
记录。确认worktree clean，记录实际start_sha，确认76b0746和e78b564均为ancestor，并确认计划
文档提交未改变effective source digest。

本轮只实现control DB v16 durable manual barrier、indexed barrier/candidate query和single
dispatcher sticky notification generation。必须保持public error、single dispatcher、global worker
bound、per-repository FIFO/mutex和no-double-claim。不得触碰marker、FULL_SCAN deadline、Arrow
bridge、S4/S6/S7或artifact cleanup协议。

按§6 Required work与Required evidence实现并验证。migration、所有FAILED/correction writers和
dispatcher reader必须同轮一致；malformed旧FAILED evidence不得静默解除barrier。idle不得周期
查询，lost wakeup必须由generation协议消除。

focused gate green后提交建议commit：
fix(repository): persist manual import barriers and wake dispatcher

输出完整batch handoff，明确current image相对本轮HEAD为stale/deferred、last verified image仍是
e78b564。报告S3-B ready yes/no后停止，不开始S3-B，不执行Step E。
```

## 7. S3-B — Bounded marker inspection

### Objective

让marker inspection的Dolt query/process count与normal branch数量无关，同时完整保留
zero/unique/ambiguous、candidate、parent和direct-ref证据。

### Allowed scope

- `versioned_import/provider.py` marker实现；
- Candidate A metadata query schema/validation中marker所需最小变化；
- marker provider tests和新的capacity/benchmark test；
- 删除确认无consumer的marker helper。

不得修改dispatcher schema、verification deadline或Arrow/read生命周期。

### Required work

1. 在固定Dolt 2.1.11的disposable repository上验证可用SQL/table function行为，保存探测命令与
   关键输出；不要依赖网络文档替代实际probe。
2. 删除“枚举每个branch并逐branch运行marker_scan”。首选single query；若固定Dolt无法一次
   返回全部必要证据，最多两次bounded query。query和process count不得随branch数增长。
3. 查询必须覆盖normal、private和MANUAL refs可达的marker evidence，不能只查当前branch。
4. 保持exact marker、unique candidate、single parent和candidate direct refs；已前进的ref不得
   作为candidate direct ref。conflicting candidates/parents、duplicate/malformed/whitespace/null/
   truncated/query fault全部ambiguous。
5. 不能用过早`LIMIT`漏掉第二个冲突marker；返回zero前必须具备完整的bounded absence证据。
6. 删除`CandidateAImportProvider._refs_for_commit`前保存全repository exact consumer `rg`，确认
   无consumer后同步删除对应dead test/mocks。
7. 新增`tests/test_import_marker_capacity.py::test_marker_query_count_is_branch_independent`。
8. 1、8、32、128 branches各warm-up后运行5次，记录query count、process count、duration和
   zero/unique/ambiguous/parent/ref语义。128-branch p95要求
   `<= max(500 ms, 3 * one-branch p95)`。
9. branch/history fixture批量构造，不在循环中反复spawn外部进程。

### Required evidence

- 既有marker malformed/fault/long-history/publish tests；
- normal/private/MANUAL ref增长与direct-ref movement；
- branch-independent query/process count；
- 1/8/32/128五次结果与p95；
- exact consumer search before delete；
- relevant integration和必要serial；
- focused ruff/mypy、pytest、`git diff --check`。

### Prompt S3-B

```text
你在 /root/gateway-data-management-system 仓库执行P2-R6-S3-B。S3-A handoff必须已提交且
worktree clean。

开始前读取p2-r6-s3-staged-execution-guide.md的§§1–5、§7、正式marker authority和完整S3-A
handoff。记录start_sha并核对S3-A的schema/dispatcher tests仍green。

本轮只实现branch-independent marker inspection、固定Dolt probe、1/8/32/128 capacity evidence和
确认无consumer后的_refs_for_commit删除。保持marker exact语义与ambiguity fail closed；最多两次
bounded query，query/process count不得随branch数增长。不得开始FULL_SCAN deadline或Arrow
bridge工作。

按§7 Required work与Required evidence执行。benchmark fixture必须批量构造并记录五次样本、
p95及query/process count。

全部gate green后提交建议commit：
fix(repository): bound marker inspection across branches

输出完整batch handoff和consumer search，报告S3-C ready yes/no后停止。不开始S3-C，不执行
Step E。
```

## 8. S3-C — Cumulative FULL_SCAN deadline

### Objective

让已有`full_scan_timeout_seconds`成为覆盖catalog和所有table的whole-verification monotonic
deadline；timeout必须取消并回收owned child，且绝不能继续publish。

### Allowed scope

- `versioned_import/verification.py`及private provider port；
- Candidate A import provider/CLI的per-call timeout与stream cancellation传递；
- worker command和startup recovery的verification调用；
- focused verification/provider/worker/recovery/process tests。

不得修改public verification policy、marker结果、dispatcher模型或Arrow HTTP bridge。

### Required work

1. FULL_SCAN进入verification时创建absolute monotonic deadline；覆盖catalog/type projection、
   plan compilation之后的provider work和全部table streams，不按table重置。
2. 每个实际CLI/provider调用前重新计算remaining，并使用
   `min(existing per-call timeout, remaining)`；catalog内部多个子查询不得复用初始remaining。
3. remaining `<= 0`时立即终止，不启动新child。deadline/cancellation必须贯穿
   `_CancellableProviderWrapper`、Candidate A iterator与`ProcessStream`。
4. timeout执行TERM/KILL/wait/reap、关闭pipe/reader并删除query temp；不能只在上层返回错误。
5. normal execute与startup recovery/continue verification共享同一实现和setting。
6. deadline发生在publish前。若main仍可证明未发布，映射为普通
   `VERIFICATION_FAILED_NOT_PUBLISHED`并收敛private ref；证据不确定仍manual。timeout后不得执行
   second-main-check或publish。
7. NONE/STRUCTURAL和requested/completed policy、unknown type、manifest/catalog、row-count及
   conversion语义不变。
8. 新增权威测试：
   - `tests/test_import_worker.py::test_full_scan_deadline_is_cumulative`
   - `tests/test_import_worker.py::test_full_scan_timeout_cancels_and_reaps`
9. 至少一条真实Dolt+serial process cleanup smoke；纯deadline arithmetic用fake clock/provider，
   不使用会`dolt init`的fixture。

### Required evidence

- catalog耗时与multi-table累计耗时均计入同一deadline；
- remaining缩短且耗尽后不启动下一调用；
- timeout main不变、无publish、stable failure正确；
- worker/recovery路径一致；
- cancellation observed、child/temp/thread zero residual；
- 既有FULL_SCAN mapping、conversion、row-count、recovery tests；
- relevant integration/serial、focused ruff/mypy、pytest、`git diff --check`。

### Prompt S3-C

```text
你在 /root/gateway-data-management-system 仓库执行P2-R6-S3-C。S3-B handoff必须已提交且
worktree clean。

开始前读取p2-r6-s3-staged-execution-guide.md的§§1–5、§8、Repository Contract verification
语义和完整S3-B handoff。记录start_sha，核对S3-B marker gate仍green。

本轮只实现FULL_SCAN cumulative monotonic deadline及normal/recovery的provider、CLI、stream
cancel/reap传递。deadline覆盖catalog和全部table，每次真实调用前重算remaining；timeout不得
publish，只有main可证明未发布时才映射普通verification failure。不得修改public policy、
dispatcher或Arrow HTTP bridge。

按§8 Required work与Required evidence实现。纯逻辑测试用fake clock；真实child cleanup测试按
integration+serial分类。

全部gate green后提交建议commit：
fix(repository): enforce cumulative full scan deadlines

输出完整batch handoff和resource cleanup结果，报告S3-D ready yes/no后停止。不开始S3-D，不执行
Step E。
```

## 9. S3-D — Event-driven Arrow lifecycle

### Objective

关闭`R5-CLEANUP-02/04/05`：移除slow-stream default-executor polling，把test probe改为instance
scope，并让disconnect/shutdown的effective cancellation最终反映到`CommandResult.cancelled`。

### Allowed scope

- `versioned_read/arrow_bridge.py`、streaming response和必要的private read wrappers；
- Candidate A row stream/process close的effective cancellation传播；
- row-stream admission/lifecycle tests、read HTTP integration和shutdown regression；
- 删除被instance probe取代的global-hook tests/mocks。

不得引入production dependency、process-wide cache、public wire或S7 Compose harness。

### Required work

1. 删除`asyncio.to_thread(queue.get, timeout=0.05)`的per-poll数据路径；使用thread-safe、
   event-driven notification连接owned producer thread和event loop。
2. 继续使用容量1的bounded bridge形成backpressure；不得整表materialize或用unbounded async
   queue替代。
3. 正常结束输出schema/batches/EOS；provider/conversion/cancel failure保持truncated stream。
4. slow consumer下不得为每batch或每50 ms调度default-executor work。已有单次bounded cleanup/
   AnyIO shield可以保留，但必须结束且zero residual。
5. 把`ArrowIpcStreamBridge`的process-global `ClassVar` barriers改为explicit、instance-scoped、
   production默认None的test probe。并发bridge的probe互不干扰，production不读取全局测试状态。
6. 删除global hooks时同步收敛只证明旧private interleaving的tests，不复制一整套新probe矩阵。
7. bridge设置cancellation后，Candidate A generator/wrapper/finally不得用普通`close()`覆盖
   effective cancel；最终`ProcessStream.close()`/`CommandResult.cancelled`为true。
8. permit只能在worker、reader、owned child和query temp清理完成后释放；open失败、disconnect、
   shutdown和持续cancel都不得泄漏。
9. 测量1/4/8 slow streams，记录default executor pending/running、bridge thread、Dolt child、
   query temp与cleanup duration。保持第九路pre-header 503。
10. `R5-CLEANUP-03`测试继续green且不修改其closed语义。

### Required evidence

- `test_slow_streams_do_not_poll_default_executor`或等价权威nodeid；
- 1/4/8 slow streams和
  `tests/test_row_stream_admission.py::test_real_rows_route_rejects_ninth_before_response_start`；
- instance probe isolation/concurrent bridges；
- disconnect/shutdown observed `CommandResult.cancelled=true`；
- backpressure、EOS/truncation、join/close、permit、child/temp cleanup；
- `test_runtime_shutdown_propagates_bridge_shutdown_error_after_releasing_resources`；
- relevant integration/serial、focused ruff/mypy、pytest、`git diff --check`。

### Prompt S3-D

```text
你在 /root/gateway-data-management-system 仓库执行P2-R6-S3-D。S3-C handoff必须已提交且
worktree clean。

开始前读取p2-r6-s3-staged-execution-guide.md的§§1–5、§9、R5 cleanup inventory和完整S3-C
handoff。记录start_sha并核对deadline/marker/dispatcher focused gates仍green。

本轮只关闭R5-CLEANUP-02/04/05：event-driven Arrow handoff、instance-scoped probes、effective
cancellation、permit与resource cleanup。保持queue capacity 1、EOS/truncation、public wire和
existing shutdown semantics；不引入dependency、process-wide cache或S7 harness。

按§9 Required work与Required evidence实现。避免以新probe复制旧private interleaving测试；
必须提供1/4/8 slow stream和第九路pre-header 503证据。

全部gate green后提交建议commit：
fix(repository): replace arrow polling with event-driven handoff

输出完整batch handoff、R5-CLEANUP-02/04/05状态和resource inventory，报告S3-E ready yes/no后
停止。不开始S3-E，不执行Step E。
```

## 10. S3-E — Post-R5 residue and source closure

### Objective

关闭`R5-CLEANUP-01/06` implementation disposition，确认`03`保持closed，执行S3跨批次source
regression、旧引用分类和candidate前清理；不增加新feature。

### Allowed scope

- 确认无consumer后的dead参数/helper/冗余分支删除；
- 对S3-A至D实际失败的owning production/test最小修复；
- S3 stage report/handoff所需的build-context外temporary evidence；
- focused、classification、static和cross-batch regression。

不得开始W1/W2、snapshot/restore、正式Compose client harness或final Phase 2 gate。

### Required work

1. 保存exact consumer search并处置至少以下residue：
   - `_as_import_provider_error`重复fallback；
   - OpenAPI `simple_error_response`死`status_code`参数；
   - `VersionedReadApplication.resolve_main`无作用re-raise；
   - S3-B未删除完的confirmed dead marker helper；
   - 与已删除global bridge hook直接绑定的dead mocks/branches。
2. 不得借cleanup改变public error mapping、marker、catalog、tar safety或Arrow contract。
3. 明确记录`R5-CLEANUP-01`为`closed_no_process_wide_cache`，保留request/session-scoped bounded
   memo；S6 capacity evidence仍deferred。不得基于无W1 measurement新增共享cache。
4. 汇总`R5-CLEANUP-02/04/05`的nodeid与measurement，确认`03`原nodeid继续通过，`06`有consumer
   search和affected tests。
5. 运行所有S3指定nodeid、marker benchmark、1/4/8 slow-stream gate、affected integration和
   serial；修复第一失败的owning scope，不写partial-pass措辞。
6. 按`AGENTS.md`移开Dolt后运行完整`repository_service -m unit`，并保证失败时也恢复binary。
7. 五个Python包分别运行`uv run ruff check .`和`uv run mypy`：`shared_kernel`、
   `repository_contracts`、`repository_service`、`repository_client`、`backend`。
8. 运行`git diff --check`、受影响dead-symbol search和execution checklist §9五组全repository
   old-reference search，人工区分current、negative与historical命中。
9. 本批不提前运行S8/S9拥有的no-ignore全量final gate，也不执行Step E。S3 source closure后先
   进入fresh independent review。

### Required evidence

- S3-A至D全部权威nodeid与实际counts；
- marker 1/8/32/128五次report；
- slow-stream 1/4/8 report与zero residual；
- parked-Dolt unit、affected integration、serial；
- five-package ruff/mypy；
- exact consumer search、old-reference classification、`git diff --check`；
- worktree clean、current image明确stale/deferred、review ready yes/no。

### Prompt S3-E

```text
你在 /root/gateway-data-management-system 仓库执行P2-R6-S3-E。S3-D handoff必须已提交且
worktree clean。

开始前读取p2-r6-s3-staged-execution-guide.md的§§1–5、§10、正式S3 exit/evidence matrix和完整
S3-D handoff。记录start_sha，核对S3-A至D commits均为ancestor。

本轮不增加feature；只关闭R5-CLEANUP-01/06 implementation disposition、确认03保持closed、
执行跨批次source regression和最小owning-scope修复。删除前保存exact consumer rg。不得新增
process-wide cache，不得声称W1/W2、S4、S6、S7或Phase 2完成。

按§10 Required work与Required evidence执行，包括parked-Dolt unit、affected integration、
serial、五包ruff/mypy、git diff --check和全repository old-reference人工分类。

全部source gate green后提交建议commit：
refactor(repository): close post-r5 operational residue

输出完整batch handoff，标记independent S3 review ready yes/no后停止。不要自行宣称S3 exit，
不要执行Step E，不开始S4。
```

## 11. Fresh independent review与finding closure

S3-E结束后必须新开对话，对包含execution baseline和S3-A至E的完整commit range做独立只读
review。reviewer先核对authority、实际diff、migration/query/index、thread/process lifecycle和
测试分类，不复述实现者handoff代替代码审计。

review至少检查：

- v15→v16 migration、所有FAILED/correction writer与barrier reader同transaction一致；
- dispatcher generation协议无query/wait lost wake、无idle polling或candidate JSON scan；
- marker query/process count真正与branch数无关，ambiguity/ref语义未缩水；
- FULL_SCAN absolute deadline进入所有catalog/table/recovery路径，timeout不publish且child/temp
  回收；
- Arrow data handoff不再轮询default executor，instance probe无global状态，effective cancel和
  permit释放顺序正确；
- R5-CLEANUP dispositions与formal plan一致，未把S6 evidence伪称为S3 pass；
- test owner、marker分类和比例化保障符合`AGENTS.md`，没有按private interleaving扩张矩阵；
- image/deployment/container-only边界没有未记录变化。

finding按severity、代码位置、业务后果和复现证据报告。实现finding时只修改owning scope，逐轮
提交并重跑affected gates；每轮记录current HEAD、container stale/deferred和last verified
`e78b564`。所有finding关闭前：

```yaml
S3_exit: no
Step_E_ready: no
P2-R6-S4_ready: no
```

## 12. S3 exact-candidate Step E

所有finding关闭、source gates green且worktree clean后，封板exact S3 code candidate。按当前
`AGENTS.md`，阶段退出必须为该candidate重建image；不得用S2 `e78b564`关闭S3。中间批次和finding
轮不重复build。

本机公共网络不可用时沿用S2已证明流程：在`10.10.60.4`创建exact candidate的clean detached
worktree，使用retained cache构建，通过可审计`docker save`/transfer/`docker load`在本机执行。
不得在本机对公网重建，也不得让remote checkout漂移到branch tip。

### Identity gate

记录并核对：

- literal code candidate SHA和remote/local clean status；
- build command、retained cache endpoint/status、build-input revision；
- helper重算的effective `source_tree_sha256`；
- remote/local image ID相等；
- `org.opencontainers.image.revision`、source-tree和uv-lock labels精确匹配；
- S2 image明确superseded for S3，不参与pass判断。

### Directed container/process gate

至少执行：

1. `docker compose ... config`，确认没有恢复broker/helper/socket/tombstone wiring；
2. fresh volume启动、`/readyz`和existing import/restart/replay Compose nodeid；
3. 受控FULL_SCAN deadline：main不发布、stable failure正确、无owned Dolt child/query temp；
4. 1/4/8 slow row streams、第九路pre-header 503；
5. 主动disconnect和runtime shutdown后bridge worker、Dolt child、query temp与permit收敛；
6. restart后ready且无遗留RUNNING process；
7. `down -v`后本gate的container/network/volume为零。

S3不提前创建S7正式Remote Client Compose nodeid；可复用现有harness或使用不提交production
surface的directed probe。任一required gate失败时S3 no-go，返回owning batch修复，产生新candidate
并重建；文档不能把失败改写为pass。

### Provenance commit

container通过后，只在verified effective digest之外提交独立provenance，例如：

`docs/backend-vnext/refactoring/temporary/p2-r6-s3-step-e-container-gate.md`

分别记录：

```yaml
validated_code_sha: <S3 exact code candidate>
container_validated_code_sha: <same S3 exact code candidate>
provenance_documentation_sha: <later docs-only commit>
image_id: <exact image id>
source_tree_sha256: <effective digest>
production_retest_required: yes
phase_2_complete: no
P2-R6-S3_exit: pass
P2-R6-S4_ready: yes
```

candidate commit不得自引用或在build后amend。provenance doc不能进入已验证effective digest；若
意外改变build input，旧image/evidence立即superseded，必须重新封板和构建。

## 13. Batch handoff template

每个S3-A至E对话结束时完整输出：

```text
round: P2-R6-S3-<A|B|C|D|E>
start_sha:
commit_shas:
head_sha:
required_ancestors:
worktree_clean: yes/no

objective_closed:
modified_scope:
deleted_scope:
explicit_non_goals_preserved:
schema_or_private_api_changes:

validation_commands:
  - command:
    result: pass/fail + exact counts/key output
first_failures_and_fixes:
consumer_search_before_delete:
old_reference_searches:
runtime_cleanup:

R5_cleanup_disposition:
known_limitations:
validated_source_scope:

Current_HEAD:
Container_rebuild_required: yes/no
Reason:
Last_verified_image_revision: e78b564a112b2a040740e3e07d7e6f04329d06e9
Last_verified_source_tree_image_id:
Container_gate_for_current_HEAD: deferred/stale/not-applicable
Deferred_gates_nodeids:
Required_execution_point: findings关闭后的S3最终候选Step E

batch_exit: pass/no-go
next_batch: P2-R6-S3-<next>
next_batch_ready: yes/no
next_entry:
```

不能用“主要通过”“仅环境失败”替代命令结果。未提交、worktree dirty、required gate失败或
authority冲突时，`next_batch_ready=no`。

新对话入口可以使用：

```text
执行P2-R6-S3-<batch>。

完整约束见：
docs/backend-vnext/refactoring/temporary/phase-2/p2-r6-s3-staged-execution-guide.md

上一批次handoff：
<paste complete handoff>

核对当前HEAD、required ancestors、worktree和上一批门禁；只执行当前batch。完成提交和handoff
后停止，不开始下一batch，不重建最终镜像。
```

## 14. Stop与reopen conditions

出现以下任一情况时停止当前批次，不用局部补丁扩大S3：

- 固定Dolt版本无法在最多两次bounded query内保持marker uniqueness/parent/ref证据；
- durable barrier需要public schema/error变化或无法在现有SQLite transaction中与FAILED状态一致；
- single dispatcher模型不足且需要多dispatcher/跨进程capacity协议；
- whole-operation deadline无法在不改变public policy的情况下取消并回收owned child；
- event-driven bridge无法在disconnect后有界退出worker/Dolt，或必须增加新production dependency；
- 真实需求要求process-wide cache、metrics platform、generic scheduler或Candidate B；
- container gate需要修改S4/S6/S7拥有的public/deployment scope；
- formal owners、本文或当前代码事实出现无法按authority顺序消解的冲突。

上述情况记录`batch_exit=no-go`、`next_batch_ready=no`，并指出需要修订的owner。普通私有API
形状、SQL索引名、fixture布局、日志文字和可逆实现选择不是reopen理由。
