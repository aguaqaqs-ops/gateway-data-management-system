# P2-R6-S4 Staged Execution Guide

状态：Temporary execution coordinator — implementation pending

日期：2026-08-14

适用：`P2-R6-S4 — Private snapshot/restore and restored lifecycle`

本文件把P2-R6正式计划中的S4拆成三个严格串行、独立提交和独立handoff的实现批次，并规定
fresh independent review与exact-candidate container gate。它不拥有public contract、磁盘格式、
恢复保证、部署拓扑或S4 exit语义；冲突时必须回到正式owner，不得用本文扩大snapshot/restore
支持面。

## 1. Authority与必读顺序

每个批次开始前至少读取本文全局规则、当前批次和上一批完整handoff，并按以下顺序处理
authority：

1. 仓库根目录`AGENTS.md`；
2. [Repository Service Contract §§3、14.1、15、17–18](../../formal/contracts/repository-service.md)；
3. [P2-R6 Operational Closure Staged Execution Plan §§3–5、S4、§§7–10](../../formal/plans/p2-r6-operational-closure-execution-plan.md)；
4. [P2 Versioned Repository Implementation Design §§6–7、18–21](../../formal/plans/p2-versioned-repository-implementation-design.md)；
5. [P2 Versioned Repository Execution Checklist §§1–2、8–10](../../formal/plans/p2-versioned-repository-execution-checklist.md)；
6. [Testing Conventions](../../../testing-conventions.md)、
   [Proportional Assurance Policy](../../formal/policies/proportional-assurance-and-risk-based-verification-policy.md)
   与[ADR 0012](../../formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)；
7. [P2-R6-S3 Step E container gate provenance](../p2-r6-s3-step-e-container-gate.md)。

正式计划冻结S4目标、non-goals和exit。本文只拥有批次顺序、最小private operator协议、focused
gate、review重点和handoff格式。普通类名、私有helper拆分、JSON字段内部组织和fixture布局由
实现者按现有代码风格保守选择，但不得改变第4节冻结的行为边界。

## 2. Entry snapshot与计划文档提交

本文编写前的已确认入口：

```yaml
branch: phase1/gate-ownership-repair
planning_base_sha: f63c39dffe3c5179d3517efb1c2809bfa6462a8f
s3_validated_code_sha: 71250c8790be6688bc9d2042e2e0a0e79a783447
s3_provenance_documentation_sha: f63c39dffe3c5179d3517efb1c2809bfa6462a8f
s3_image_id: sha256:0d0f6b4f9c547de5a0635b9af20175507e606028e1641e7064c567184d5a093f
s3_source_tree_sha256: sha256:5222659983e79f8f4c9a548fc6f9a749b66bffdd1c13c2aeec9278522349e6c0
s3_container_gate: passed
s3_exit: pass
s4_entry_ready: yes
phase_2_complete: no
production_retest_required: yes
```

S4的Git开发起点是包含S3 provenance修正的计划文档commit，不是回退到
`s3_validated_code_sha`。S3 image只证明`71250c8`；第一处S4 production/build-input变化后它
立即成为ancestor evidence，不得表述为当前HEAD已通过container gate。

本文和Phase 2临时索引先形成独立docs-only clean commit。S4-A执行者记录实际`start_sha`，
确认`planning_base_sha`与`s3_validated_code_sha`均为ancestor，并用唯一digest helper确认计划
提交未改变Repository Service effective source digest。计划提交SHA只写入外部handoff，不在
本文中递归回填自身SHA。

## 3. S4目标、范围与non-goals

### 3.1 Stage outcome

S4必须同时完成：

- private operator `snapshot hold`在Service停止时取得durable-root exclusive lock；
- `hold`完成SQLite WAL checkpoint、确认无open writer，输出machine-readable ready evidence，
  并持续持锁直到operator结束helper；
- 外部设施只在ready窗口内一次性snapshot整个data root；
- private operator `snapshot check`在Service仍停止时校验whole-root restore的layout、SQLite
  integrity、artifact/control binding与全部已登记Dolt repository可读性；
- 从空目标root恢复后使用相同支持版本启动，通过ready、integrity和expected public facts；
- success、failure、signal和restart路径均无provider/process/thread/query-temp残留；
- operator runbook能够逐命令执行，不依赖未提交脚本、未说明的host状态或隐式人工步骤。

### 3.2 Allowed scope

- private snapshot admin module及其最小共享helper；
- `DurableRootLock`、`ControlStore`、`DurableLayout`和offline provider的必要private adapter；
- private CLI的container invocation/runbook；
- focused unit、真实Dolt integration、serial与directed container probe；
- S4 source/container provenance文档。

允许复用`versioned_import/admin.py`中的stopped-service惯例，但snapshot命令不得塞入manual import
recovery语义或让两个admin domain互相依赖。优先使用独立的private module，例如
`python -m gateway_repository_service.snapshot_admin ...`，不新增production dependency。

### 3.3 Explicit non-goals

所有批次共同禁止：

- public backup、restore、repair、delete、GC route、DTO或error code；
- online snapshot、per-repository snapshot、incremental snapshot、overlay restore；
- RPO/RTO、每commit同步备份或CommitId跨灾难稳定保证；
- cross-version restore、layout migration、自动修复或自动package replay；
- snapshot scheduler、daemon、sidecar、broker、socket、pidfile、独立UID或新service；
- NFS/SMB/RWX/FUSE/tmpfs支持或multi-node/shared writable root；
- 持久snapshot evidence ledger、manifest state machine、quarantine/tombstone；
- S5 build provenance重构、S6 W1/W2、S7正式Compose lifecycle harness、S9/S10 final gate；
- 以private interleaving矩阵替代whole-root行为测试；
- 在一个批次中顺带开始下一批或P2-R6-S5。

## 4. Frozen private operator protocol

### 4.1 Common boundary

- 命令只作为private operator CLI运行，不注册ASGI route、OpenAPI或client surface。
- operator与Service属于Contract已接受的同一可信部署域，但仍必须保持server-owned root、
  containment、symlink、regular-file、非shell执行和secret/log脱敏边界。
- CLI只绑定已存在的root；除`hold`执行必要的SQLite checkpoint外，不创建layout、不迁移schema、
  不修复文件、不启动Service或provider server。
- stdout只输出单行、版本化、machine-readable JSON summary；stderr用于稳定的人类可读错误。
  不输出token、SQL、provider stderr、raw row、host/internal path或private ref。
- exit code是private operator contract，可在S4-A冻结并测试；不得映射为新的public error。

### 4.2 `snapshot hold`

固定顺序：

1. 以只读方式绑定existing layout并验证root/component containment；
2. 非阻塞取得`control/service.lock`的exclusive `flock`；失败即证明Service或另一operator仍拥有root；
3. exact-version、`allow_migration=False`打开control DB；
4. 执行`PRAGMA wal_checkpoint(TRUNCATE)`或等价的同语义adapter，只有busy为零且无未checkpoint
   frame时才继续；
5. 关闭control DB connection并flush ready JSON到stdout；ready evidence不得先于checkpoint成功；
6. helper保持root-lock file descriptor，不轮询DB、不启动child，等待operator结束；
7. `SIGINT`/`SIGTERM`是受控结束，释放lock并有界退出；未输出ready前的signal或任何错误为失败。

ready JSON至少能区分schema版本、`action=hold`、`status=ready`、layout format、control DB版本和
checkpoint结果；不得包含可变host path。它只是本次进程输出，不写入durable root，也不形成
新的evidence状态机。

不引入stdin协议、socket、后台daemon或“ready文件”。外部设施只能在看到完整ready JSON且
确认helper仍存活后snapshot；helper退出即表示窗口关闭。

### 4.3 `snapshot check`

固定边界：

1. restore copy由外部operator设施完成；CLI不复制、解包或覆盖数据；
2. operator/runbook在restore前证明目标root为空。`check`不通过新增持久sentinel事后猜测目标
   是否曾为空；directed harness拥有该前置条件的证据；
3. restore完成后Service仍停止，`check`取得同一exclusive root lock；
4. 使用`lstat`/descriptor-safe检查拒绝root逃逸、required component symlink、non-directory和
   跨filesystem component；
5. 校验layout marker与当前支持的layout format，control DB exact version、schema、
   `integrity_check`和foreign-key integrity；不migration、不checkpoint修复损坏状态；
6. 按当前repository/artifact lifecycle校验control DB durable binding与root内实际对象；已按
   现有规则清理的eligible artifact bytes不因缺失被误判为损坏，允许的ordinary residual也不
   被升级为新Contract；
7. 对每个已登记Versioned repository执行bounded、offline、read-only Dolt可读性检查；
8. 输出单行`action=check`、`status=passed` JSON后退出并释放lock。任一检查失败时非零退出，
   不输出passed、不启动Service、不修改恢复内容。

`check`通过只表示该whole root可以进入same-version startup验证；它不单独证明public facts，
也不把S7/S10 restored lifecycle gate提前标为完成。

### 4.4 Container invocation

private helper必须以最终Repository Service image中的gateway euid和同一named volume运行。
operator命令应覆盖普通server command/entrypoint，避免`docker-entrypoint.sh`在检查前创建或修改
layout；不得为S4增加常驻Compose service。建议runbook使用一次性`docker compose run --rm
--no-deps --entrypoint python --user gateway ... -m gateway_repository_service.snapshot_admin`或等价
可审计命令。

## 5. Cross-batch invariants

1. S4-A、B、C严格串行。每批从上一批clean green commit开始，提交并输出完整handoff后停止。
2. A只交付可用的hold纵切；B在其协议上增加check；C关闭whole-root lifecycle、runbook和source
   gate。不得提交只有parser而没有owning behavior的空壳。
3. root lock是Service与offline operator的唯一ownership boundary；不得再建第二套lock、lease、
   heartbeat或persistent ownership record。
4. ready/passed evidence只在所有前置检查完成后输出；partial stdout、异常或nonzero exit不得被
   runbook解释为可继续。
5. failed hold/check从不复制、覆盖、删除或修复root，也不自动启动Service。operator必须保持
   Service stopped并人工处置。
6. snapshot与restore单位始终是整个mounted data root；SQLite-only、单个Dolt tree和component
   overlay均为no-go。
7. same-version只接受当前支持的layout/control schema/Dolt版本；S4不实现兼容adapter或migration。
8. 测试按Contract行为命名，每个不变量只有一个权威owner。仅payload/错误不同的同构case使用
   模块级共享参数表。
9. 使用真实Dolt、`ServiceRuntime.start()`、subprocess或落盘provider的测试标`integration`；依赖
   Event/signal/process timeout相对预算的测试同时标`serial`并以`-n 0`运行。
10. 纯parser、JSON shape和path校验测试不得创建真实Dolt HOME；新Dolt HOME必须预置关闭
    versioncheck的private config。
11. 每批保存删除/移动symbol前的exact consumer `rg`，运行受影响scope旧引用搜索；S4-C做全仓
    人工分类。
12. A/B中间批次不重建image，但handoff必须写当前container gate为`stale/deferred`，last verified
    image仍绑定S3 `71250c8`。finding关闭后的S4 exact candidate必须重建一次。
13. candidate封板后不得amend/rebase/squash；provenance只写入effective digest之外的后续提交。

## 6. Delivery sequence与conversation protocol

```text
docs-only execution baseline
  -> S4-A snapshot hold vertical slice
  -> S4-B snapshot check vertical slice
  -> S4-C restored lifecycle, runbook and source closure
  -> fresh independent S4 review and finding closure
  -> exact-candidate Step E and provenance
  -> P2-R6-S5 handoff
```

| Batch | Outcome | Suggested commit |
| --- | --- | --- |
| S4-A | stopped-service lock、WAL checkpoint、ready JSON、signal-safe hold | `feat(repository): add private snapshot hold tooling` |
| S4-B | whole-root layout/control/artifact/Dolt integrity check | `feat(repository): validate restored repository roots` |
| S4-C | empty-target restore procedure、same-version lifecycle、runbook、source closure | `docs(repository): close snapshot recovery lifecycle` |

每批使用新对话，禁止并行。新对话只接收本文、上一批完整handoff和当前批prompt。整体review与
Step E分别使用新的干净对话；review者不以实现者handoff替代代码审计，Step E不夹带production
修改。

## 7. S4-A — Snapshot hold vertical slice

### Objective与allowed scope

实现第4.2节完整hold纵切。允许修改private snapshot admin module、最小root-lock/control DB
adapter、focused tests和必要的package documentation。不得实现restore copy、Dolt check、
public route、Compose wiring或S4-B逻辑。

### Required work

- 复用`DurableLayout.bind_existing`与`DurableRootLock`，补足不改变正常runtime语义的private安全
  adapter；
- exact-version、no-migration WAL checkpoint API返回可判定的busy/frame结果；
- 单行ready JSON必须写出并flush后才进入hold；
- SIGINT/SIGTERM、broken stdout、checkpoint busy/error和root-lock busy都释放已取得资源；
- helper持有lock期间，Service与第二个admin helper都必须fail closed；
- 不使用轮询DB或sleep保持窗口，等待实现应是signal/event-driven；
- 冻结private exit code与runbook可消费的stdout/stderr边界。

### Required evidence

至少覆盖：

- `test_hold_checkpoints_and_holds_root_lock`：ready前完成checkpoint，ready后lock仍被占有；
- running Service/另一个holder导致hold非零退出且无ready；
- active SQLite reader/writer使checkpoint不能满足条件时fail closed；
- SIGINT、SIGTERM和异常stdout路径有界释放lock/connection；
- malformed/missing/newer/older control DB不被创建或迁移；
- machine JSON无host path、secret、SQL或provider stderr；
- parked-Dolt `-m unit`证明纯逻辑测试未误用真实provider。

阶段门禁：focused unit/integration、相关serial `-n 0`、repository_service ruff/mypy、
`git diff --check`。真实signal/process测试必须serial。完成green commit和handoff后停止。

### Prompt S4-A

```text
执行P2-R6-S4-A。完整约束见
docs/backend-vnext/refactoring/temporary/phase-2/p2-r6-s4-staged-execution-guide.md。

开始前读取§§1–7及正式snapshot/restore authority，记录start_sha，确认S3 candidate、provenance、
planning docs均为ancestor且worktree clean。只实现snapshot hold完整纵切：stopped-service root lock、
WAL checkpoint、ready JSON、signal-safe hold与focused tests。不得开始check/restore、修改public API或
Compose。通过required gates后提交、输出§13 handoff并停止。
```

## 8. S4-B — Snapshot check vertical slice

### Objective与allowed scope

实现第4.3节restored-root check，复用A的private CLI/lock/error约定。允许修改snapshot admin、
layout/control DB/offline Dolt的最小read-only adapter与focused tests。不得复制snapshot、实现
online restore、增加migration或开始S4-C container lifecycle。

### Required work

- 在任何内容检查前取得root lock，lock busy时不打开provider；
- 验证resolved root、required component、same-filesystem、symlink与regular-file边界；
- exact-version readonly control DB执行schema、`integrity_check`与foreign-key检查；
- 从权威control数据取得应存在的repository/artifact binding，验证server-owned containment、
  类型、必要size/digest与存在性；
- 对全部已登记Dolt repository做offline read-only可读性检查，child/temp始终有界回收；
- 允许Contract定义的ordinary staging/residual存在，不为derived state建立强一致性manifest；
- 任一partial/missing/corrupt/mismatched状态非零退出且不输出passed、不修改root；
- check通过只输出safe counts/version/result，不暴露repository path或raw identifier。

### Required evidence

使用模块级共享fault table覆盖layout marker、component symlink/cross-root、control DB
missing/corrupt/version/schema/FK、artifact binding和Dolt unreadable。另至少覆盖：

- valid whole-root check通过且child/temp为零；
- running Service时check在provider启动前失败；
- 多repository检查不遗漏且错误定位不暴露path；
- check不改变受检root的业务文件、schema version或repository HEAD；
- provider失败/取消后child与query temp收敛。

运行focused unit、真实Dolt integration、serial `-n 0`、repository_service ruff/mypy、
`git diff --check`。完成green commit和handoff后停止。

### Prompt S4-B

```text
执行P2-R6-S4-B。开始前读取S4 guide §§1–6、§8、正式Contract §15和完整S4-A handoff；核对A commit
为ancestor且worktree clean。只实现restored-root check：root/layout/control/artifact binding和
offline Dolt readability，保持read-only/no-migration/no-repair。不得复制root、开始container
lifecycle或修改public API。通过required gates后提交、输出§13 handoff并停止。
```

## 9. S4-C — Restored lifecycle, runbook and source closure

### Objective与allowed scope

把A/B helper组成可执行的whole-root operator流程，关闭same-version restored lifecycle、runbook、
source regression和S4 code candidate准备。允许修改snapshot focused tests/support、operator
runbook和必要的非production directed probe；除修复本批发现外不再增加helper feature。

### Required work

- 写明host/Compose两套可审计命令：停止Service、启动hold、解析ready、snapshot whole named
  volume、结束hold、确认空restore target、restore whole root、运行check、same-image启动；
- runbook明确entrypoint override与gateway euid，不能先运行会创建layout的普通entrypoint；
- 建立fresh root → import/read → snapshot → mutate → empty-target restore → check → restart纵切；
- 保存snapshot时的expected public facts；恢复后通过HTTP/client重新验证，而不是直接读内部DB
  代替public事实；
- 验证snapshot之后的mutation不被误认为snapshot内事实；不承诺CommitId跨另一场灾难重放稳定；
- partial component、SQLite-only、single-Dolt、non-empty overlay target和live-root操作全部fail closed；
- 结束后provider/process/thread/query-temp与本轮container/network/volume inventory为零；
- 保存全仓old-reference搜索与人工分类，不删除historical ADR；
- 完成parked-Dolt unit、affected integration/serial、五包ruff/mypy和source functional gate。

### Source gates

至少执行并逐项记录：

```bash
cd vnext/repository_service
uv run pytest -m unit
uv run pytest -m 'integration and not serial' --ignore=tests/test_import_compose_e2e.py
uv run pytest -m serial -n 0 --ignore=tests/test_import_compose_e2e.py

cd vnext/<each-python-package>
uv run ruff check .
uv run mypy

./vnext/scripts/run-tests.sh --ignore=tests/test_import_compose_e2e.py
git diff --check
```

若S4新增真实Docker测试文件，source gate的ignore inventory必须登记其精确path/nodeid；静态
Docker/Compose/build tests不得排除。`-m unit`另按`AGENTS.md`移开Dolt验证并可靠恢复binary。

当前formal old-reference五组搜索全部执行；另搜索`backup|restore|snapshot`并人工区分当前
private S4语义、其他业务Snapshot概念和historical材料，不能机械删除同名但不同domain的代码。

### Prompt S4-C

```text
执行P2-R6-S4-C。开始前读取S4 guide §§1–6、§9、testing conventions、formal evidence matrix和完整
S4-B handoff；核对A/B commits为ancestor且worktree clean。只关闭whole-root restored lifecycle、
operator runbook、source regression和最小owning-scope修复。不要执行final image build，不开始S5、
S6或S7正式harness。全部source gate green后提交、输出§13 handoff，标记independent review ready并
停止。
```

## 10. Fresh independent review与finding closure

S4-C结束后新开对话，对planning baseline与S4-A至C完整range做独立只读review。reviewer先核对
authority、实际diff、WAL/lock顺序、path/layout/control binding、offline Dolt lifecycle、测试分类
和runbook命令，不复述handoff代替代码审计。

至少检查：

- ready绝不早于checkpoint完成，checkpoint busy/error不会产生可误读ready；
- helper持锁期间Service/另一helper不能取得root ownership，无polling或lost signal；
- signal、broken pipe、SQLite/provider异常均有界释放connection/lock/child/temp；
- check不migration、不repair、不启动server，不在取得lock前读取可变provider状态；
- root/component symlink、containment、same-filesystem和empty-target operator边界未缩水；
- artifact/control binding验证当前authoritative/durable facts，不把derived residual升级为新Contract；
- 每个已登记Dolt repository可读，ambiguity/corruption fail closed；
- runbook不通过普通entrypoint预先修改restore root，不依赖未提交host脚本；
- public route/OpenAPI/contracts/client无变化，S5/S6/S7证据未被伪称为S4 pass；
- marker分类、测试owner和比例化保障符合`AGENTS.md`。

finding按severity、位置、业务后果和复现证据报告。只修改owning scope，逐轮提交并重跑affected
gates。所有finding关闭、source gates green且worktree clean前：

```yaml
S4_exit: no
Step_E_ready: no
P2-R6-S5_ready: no
```

## 11. S4 exact-candidate Step E

finding关闭后封板exact S4 code candidate。S4 helper与restored volume正确性依赖container user、
entrypoint override、mount和signal边界，因此必须为该candidate重建image；不得用S3
`71250c8`/`0d0f6b4`关闭S4。

### Identity gate

沿用S3已证明的clean detached worktree、retained cache、`docker save | load`流程，记录并核对：

- literal 40-character candidate SHA、local/remote clean status；
- build command、cache status、build-input revision；
- helper重算的effective `source_tree_sha256`与uv-lock SHA；
- remote/local image ID相等；
- image revision/source-tree/uv-lock labels精确匹配；
- provenance doc不进入verified effective digest。

任何truncated/non-resolving SHA、label/digest mismatch或build-input漂移都是identity gate失败，必须
修复后重建，不能只改报告文字。

### Directed container/process gate

至少执行：

1. `docker compose ... config`，确认未新增public route、常驻snapshot service、broker/helper
   socket或额外volume wiring；
2. fresh named volume启动candidate Service，创建/import并通过HTTP/client读取expected facts；
3. 停止Service，以gateway euid和entrypoint override启动`hold`，解析完整ready JSON；
4. hold存活时启动Service和第二helper均因root lock失败；
5. ready窗口内snapshot整个named volume，结束helper并确认lock释放；
6. 重新启动原root并产生snapshot之后的mutation，然后停止；
7. 确认新restore volume为空，再restore entire root；partial/SQLite-only/single-repository和
   non-empty overlay procedure必须被拒绝；
8. 在restored volume运行`check`，same image启动后`/readyz`、integrity和snapshot时public facts
   通过，snapshot后mutation不出现；
9. corrupt/control mismatch/Dolt unreadable directed case非零退出且root未被自动修改；
10. teardown后helper/Service/Dolt child/query temp/container/network/volume为零。

S4不提前创建S7正式fresh/restart/restored Compose nodeid；可复用现有Compose与不进入production
surface的directed probe。任一required gate失败时S4 no-go；production/build-input修复产生新
candidate并重建，不能用旧image evidence关闭。

### Provenance

container通过后，只在verified effective digest之外提交独立记录，例如：

`docs/backend-vnext/refactoring/temporary/p2-r6-s4-step-e-container-gate.md`

外部handoff记录：

```yaml
validated_code_sha: <exact S4 code candidate>
container_validated_code_sha: <same S4 candidate>
provenance_documentation_sha: <later docs-only commit>
image_id: <exact image id>
source_tree_sha256: <effective digest>
production_retest_required: yes
phase_2_complete: no
P2-R6-S4_exit: pass
P2-R6-S5_ready: yes
```

## 12. Validation与container记录规则

每批报告都必须包含：

```text
Current_HEAD:
Container_rebuild_required: yes/no
Reason:
Last_verified_image_revision: 71250c8790be6688bc9d2042e2e0a0e79a783447
Last_verified_source_tree_image_id:
Container_gate_for_current_HEAD: deferred/stale/passed
Deferred_gates_nodeids:
Required_execution_point: findings关闭后的S4最终候选Step E
```

A/B/C普通Python实现可把build合并到S4 Step E，但旧镜像只能称为S3 ancestor evidence。若中间批
修改Dockerfile、entrypoint、Compose、dependency lock、container harness、UID/GID或mount/signal
wiring，则命中`AGENTS.md`强制重建边界，不能用本节默认延期覆盖。

## 13. Batch handoff template

每个S4-A至C对话结束时完整输出：

```text
round: P2-R6-S4-<A|B|C>
start_sha:
commit_shas:
head_sha:
required_ancestors:
worktree_clean: yes/no

objective_closed:
modified_scope:
deleted_scope:
explicit_non_goals_preserved:
private_api_or_disk_changes:

validation_commands:
  - command:
    result: pass/fail + exact counts/key output
first_failures_and_fixes:
consumer_search_before_delete:
old_reference_searches:
runtime_cleanup:

known_limitations:
validated_source_scope:

Current_HEAD:
Container_rebuild_required: yes/no
Reason:
Last_verified_image_revision: 71250c8790be6688bc9d2042e2e0a0e79a783447
Last_verified_source_tree_image_id:
Container_gate_for_current_HEAD: deferred/stale/passed
Deferred_gates_nodeids:
Required_execution_point: findings关闭后的S4最终候选Step E

batch_exit: pass/no-go
next_batch: P2-R6-S4-<next>
next_batch_ready: yes/no
next_entry:
```

不能用“主要通过”“仅环境失败”替代命令结果。未提交、worktree dirty、required source gate失败、
authority冲突或container trigger未处理时，`next_batch_ready=no`。

新对话入口：

```text
执行P2-R6-S4-<batch>。

完整约束见：
docs/backend-vnext/refactoring/temporary/phase-2/p2-r6-s4-staged-execution-guide.md

上一批次handoff：
<paste complete handoff>

核对当前HEAD、required ancestors、worktree和上一批门禁；只执行当前batch。完成提交和handoff后
停止，不开始下一batch，不提前重建最终镜像。
```

## 14. Stop与reopen conditions

出现以下任一情况时停止当前批次，不用局部补丁扩大S4：

- 真实需求要求public/online/per-repository/incremental snapshot或明确RPO/RTO；
- 需要cross-version migration、CommitId灾难稳定或自动package replay；
- target filesystem是NFS/SMB/RWX/FUSE/tmpfs或shared writable root；
- `DurableRootLock`不足以排除实际Service/operator writer，需要新lease/broker/sidecar/UID；
- helper必须取得root、额外capability、host socket或常驻daemon才能完成目标；
- empty-target/whole-root边界无法由当前operator设施证明，必须新增durable manifest状态机；
- artifact/control binding没有当前authoritative consumer，验证要求会创造新的业务事实；
- supported Dolt/SQLite无法在stopped-service窗口完成checkpoint或read-only integrity；
- container gate需要修改S5/S6/S7拥有的public/deployment scope；
- formal owners、本文或代码事实出现无法按authority顺序消解的冲突。

上述情况记录`batch_exit=no-go`、`next_batch_ready=no`并指出需要修订的owner。普通private类名、
exit code数值、fixture布局、JSON字段顺序和可逆helper拆分不是reopen理由。
