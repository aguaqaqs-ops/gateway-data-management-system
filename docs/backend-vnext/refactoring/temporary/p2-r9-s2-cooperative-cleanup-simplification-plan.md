# P2-R9-S2 Cooperative Artifact Cleanup Simplification Plan

状态：Temporary execution guide — implementation pending

日期：2026-08-13

设计基线：`3616ef0d9707e6ec165376d175003ca80843ab1a`

工作树（Step A 起）：`fb066194dbfea984a8e87c72a1284c9df19927b8`（基线之后的文档提交
`c6369a3` 与 cleanup 优化修复）。调用图与 schema inventory 见第 8 节。

权威语义：

- [ADR 0012](../formal/adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)
- [Repository Service Contract §3/§12/§17](../formal/contracts/repository-service.md)
- [P2-R6 Operational Closure Plan §4.1](../formal/plans/p2-r6-operational-closure-execution-plan.md)
- [Testing Conventions](../../testing-conventions.md)

本文只负责拆分实现、迁移、验证和提交顺序；与上述正式文档冲突时以上述文档为准。完成并经
独立复审后，本文件转为historical或删除，不升级为长期第二权威。

## 1. Why this needs a separate plan

这不是局部cleanup重写。当前设计同时穿过：

- production Python filesystem协议与约2,700行cleaner；
- broker client/server、Unix socket、SCM_RIGHTS、pidfd与线程/目录锁；
- control DB v9–v15 delete intent、generation、receipt、residual proof与cleanup cursor；
- worker、startup recovery、admin、upload publication/admission和runtime shutdown；
- Dockerfile、entrypoint、Compose、双UID、ownership/readiness与实际container e2e；
- `test_artifact_cleanup.py` 11,667行、181个测试函数及跨文件broker/runtime/compose测试。

把旧5项Finding逐个修好再做简化会产生一次性代码和重复验证；把所有删除压成一个提示词则
难以审查legacy volume、DB constraint、运行时中间态和测试删减是否遗漏。因此采用分阶段前向
简化，但只在最后container边界稳定后构建一次镜像。

## 2. Threat model and non-goals

实现必须按ADR 0012工作：

- Service、worker、recovery、admin和cleaner是同一可信部署域内的协作actor；
- 不抵御已经取得Service euid、durable-root写权限或宿主机管理权的恶意actor；
- 继续抵御caller path、archive traversal、symlink/root逃逸、错误repository scope、误删
  protected artifact和普通协作竞态；
- package是临时可重放输入；Dolt commit、main CAS、control DB和operation result仍是高价值边界；
- 不新增public API，不降低import CAS/idempotency/recovery语义，不重写无关R6功能。

明确不做：

- 不先修复broker安全边界再删除broker；
- 不证明同euid inode-CAS unlink，不引入新helper、sidecar或ownership token；
- 不降低control DB user_version，不做仅为清理旧列的破坏性table rebuild；
- 不保留按Round编号组织的实现考古测试；
- 不在每个中间提交重建Docker image。

## 3. Previous five findings under ADR 0012

| Previous finding | New disposition | Required implementation outcome |
| --- | --- | --- |
| F1 `gateway`可替换整个`artifacts` root，broker的`/proc/self/fd`前缀/mount-id不能证明冻结root ancestry | **撤销其“同euid攻击者突破broker”P1结论**；该攻击者已在范围外。但保留低成本root confinement要求 | 删除broker ancestry/capability证明；单一Service创建server-owned layout。普通代码仍用固定data root、dirfd、`O_NOFOLLOW`/symlink与scope检查，不接受caller path，不越出artifact root |
| F2 `_DirLocks` refcount错误可让同inode出现两把锁 | **真实broker并发bug，但不单独修复broker** | 删除`_DirLocks`及broker server。所有协作cleanup入口复用既有artifact admission pin/per-artifact锁；保留一个worker/cleaner协作互斥测试，不移植broker三参与者攻击probe |
| F3 startup helper join失败后`os._exit`会释放root lock，测试mock掩盖真实行为 | **真实helper lifecycle缺陷，由删除helper关闭** | 删除broker start/join/retain与pidfd监督；Runtime恢复普通顺序：停止intake → drain worker → stop/join cleaner → close DB → release root lock。join失败必须明确startup/shutdown失败，不得用mock宣称进程退出后仍持kernel lock |
| F4 4个partial control frames可占满control executor | **broker私有攻击面，范围和组件一并删除** | 删除data/control broker socket、frame parser、executor与相应fuzz/饱和测试；不为同UID本地恶意client建立替代协议 |
| F5 socket pathname出现早于`listen`，client connect无重试，entrypoint可误判ready | **真实broker启动可用性bug，由删除socket依赖关闭** | 删除socket wait/ping/bind readiness与helper guard；Service readiness只检查实际保留的root lock/layout/control DB/provider/disk。最终Compose从全新volume验证启动、ready、import、restart/replay |

在最终简化完成前，不得把现有broker HEAD声明为S3 ready；但实现者不需要为将删除的组件提交
过渡修复。若某项通用不变量在broker删除后仍存在，应以新组件/Contract行为重新报告，而不是
沿用旧攻击叙事。

## 4. Target behavior

### 4.1 New artifacts

1. Upload继续在server-owned staging中bounded写入、计算size/SHA并atomic publish到exact UUID名。
2. Worker/recovery/admin/cleaner调用同一个cleanup service；不得各自复制eligibility或filesystem
   分支。
3. Cleanup取得admission pin，随后在同一临界区重读完整durable eligibility。
4. Ready root通过server-owned layout取得dirfd；拒绝caller path、symlink、非regular与scope
   不一致。对exact名使用普通dirfd-relative unlink。
5. 只有artifact已经eligible时，absent/`ENOENT`才视为幂等完成并允许记录
   `bytes_deleted_at`；ineligible missing仍按readiness/integrity既有语义fail closed。
6. `EPERM`、`EIO`及其他I/O错误不改变commit/result，不伪造deleted stamp，记录脱敏诊断并
   等待后续sweep。
7. 新路径不创建或迁移到quarantine/detach/unlink-verify/stage/reclaim sidecar，不写delete
   generation、receipt或residual proof。

### 4.2 Legacy state

开始编码前先列出v15 schema CHECK、projection与所有旧sidecar parser的实际依赖，形成一张
「停止写入 / 兼容读取 / 可删除」表。默认策略：

- 不降低user_version；不为美观drop旧列。没有constraint阻碍时，旧列保留为nullable/inert
  compatibility ballast；
- startup/cleaner在root lock下有界识别已知legacy名；durable lifecycle已经eligible且对象
  可解释时按普通unlink/rmdir best effort处理；
- protected、nonzero矛盾、畸形、symlink或I/O失败对象保留并诊断，不阻塞其他candidate；
- active intent/receipt/proof若会阻断新admission，必须有一次性、可重复的兼容投影或明确
  operator诊断；不得简单把所有历史行洗白；
- 只保留最小磁盘fixture矩阵：legal eligible、protected、malformed/ambiguous、I/O failure。

若生产尚无需要保留的Round 8–22 durable volume，可以在实现报告中给出证据并进一步缩小
legacy路径；不能仅凭“内部格式”自行假设不存在存量。

### 4.3 Capacity and scheduling

- 保留free-disk admission、upload/import并发上限、cleaner sticky wake与fallback interval；
- 保留INTEGER cleanup cursor、keyset分页、poison隔离和共享SQLite transaction等独立于broker
  且已经解决真实功能/性能问题的改动；
- 删除`artifact_tombstone_budget`设置、Compose环境变量、projected reservation和只为永久
  sidecar inventory服务的计数；
- unknown entries只做有界、脱敏inventory，不递归chown/delete，不使一个poison对象饿死其他
  lifecycle candidate。

## 5. Test replacement, not additive probes

先创建面向Contract的新测试清单，再删除旧测试；不得在11,667行文件末尾继续追加一轮probe。
目标不是机械达到某个行数，而是让每个不变量只有一个owner。建议拆为：

- `test_artifact_retention.py`：纯eligibility/TTL/protected矩阵；
- `test_artifact_cleaner.py`：正常删除、eligible absent、I/O retry、pagination、shutdown；
- `test_artifact_cleanup_integration.py`：真实worker/recovery/admin、restart和legacy disk fixture；
- upload/admission与Compose断言留在各自既有owner文件。

最小语义矩阵：

1. SUCCEEDED matching consumed立即eligible；scope/result mismatch或无consumed不eligible；
2. ordinary FAILED TTL边界、orphan TTL边界；
3. PENDING/QUEUED/RUNNING/manual FAILED保留；
4. success result先持久化，cleanup成功/失败均不改业务结果；
5. eligible exact ready删除，eligible absent幂等；ineligible absent仍不被“洗白”；
6. symlink、nonregular、unknown、跨repo/root对象保留并脱敏诊断；
7. admission与cleaner协作race使用同一pin，不删除新PENDING/正在读取的bytes；
8. `EPERM/EIO`保留并在故障解除后重试；
9. startup/restart处理一个成功残留和一个legacy合法fixture，不阻塞poison后的candidate；
10. cleaner分页、notification/fallback与shutdown无线程泄漏；
11. worker/recovery/admin复用同一cleanup入口；
12. Compose全新volume完成upload/import/success cleanup/restart replay。

删除：所有只证明broker peer/capability/frame/fd/pidfd/双UID，或quarantine/detach/
unlink-verify/generation/receipt/proof syscall窗口的测试。安全相关的范围外probe不要求实现者补写。
若保留某个旧回归，必须在报告中写明它对应上面哪个Contract不变量，并去掉`rNN_`命名。

## 6. Staged implementation and commits

### Step A — Characterize and cut a simple seam

- 建立当前production call graph与legacy schema/sidecar inventory；
- 为统一cleanup service写新的Contract测试，允许它最初适配旧实现；
- 确认worker/recovery/admin/cleaner所有入口与锁序；
- 不修改Docker，不构建image。

建议提交：`test(repository): freeze cooperative artifact cleanup contract`

### Step B — Replace the production cleanup protocol

- 实现单一路径的pin → eligibility → dirfd unlink → stamp/retry；
- 停止创建sidecar、intent generation、receipt/proof与tombstone reservation；
- 保留必要legacy read/convergence适配，不做schema downgrade；
- 删除不再可达的cleaner分支与store投影；
- 验证 **不** 要求 `tests/test_artifact_cleanup.py` 全绿（该文件留到 Step D 删除）。
  focused 门禁：新 Contract 三文件 + `test_import_worker.py` +
  `test_mutation_reconciliation_import.py` + 五包 ruff/mypy。parked-Dolt `-m unit` 抽查；
- 纯Python阶段可暂缓Docker。双 UID 容器在 Step C 改 layout 所有权之前不可部署。

建议提交：`refactor(repository): restore cooperative artifact cleanup`

### Step C — Remove broker and deployment boundary

- 删除broker client/server、socket/control protocol、SCM_RIGHTS、pidfd、helper guard与runtime
  supervision；
- Dockerfile/entrypoint/Compose回到单一Service主体，删除broker UID/GID、socket、peer GID和
  tombstone budget接线；
- layout在server-owned root下创建artifact目录，保持container non-root和固定权限；
- 更新README/静态deployment测试，但先不为中间commit重复build。

建议提交：`refactor(repository): remove artifact directory broker`

### Step D — Delete superseded proof wall

- 用新owner文件替换`test_artifact_cleanup.py`；
- 删除Round 8–22实现考古、broker fuzz/security与已无生产分支的fixture/helper；
- 运行normal和parked-Dolt unit、focused integration、serial cleanup、五包ruff/mypy、
  `git diff --check`；
- 静态扫描不得残留production broker/socket/pidfd/sidecar creation或`rNN_`权威nodeid。

建议提交：`test(repository): replace artifact cleanup proof wall with contract coverage`

### Step E — One final container gate

本轮必然触发Docker重建，但只对实现收敛后的最终HEAD执行一次：

- 构建当前HEAD并核对revision/source-tree/image digest；
- `docker compose config`确认已移除broker UID/socket/tombstone budget，保留必要Service设置；
- 从全新volume运行import/restart/replay Compose nodeid；
- 如支持既有volume升级，再运行一个v15 legacy fixture容器探针；
- 记录用户、目录owner/mode、readyz、成功cleanup、restart与资源残留。

任何Step E失败先修代码再重建最终HEAD；不得用`3616ef0`或其他祖先镜像关闭门禁。

## 7. Review gates

独立复审按以下顺序：

1. authority：ADR 0011保持Superseded，代码/测试不得重新扩大威胁模型；
2. behavior：protected retention、business success与cleanup failure隔离；
3. filesystem：server-owned root、caller path拒绝、dirfd/symlink/scope基本边界；
4. concurrency：所有协作入口共用pin与eligibility，没有重复私有删除协议；
5. compatibility：v15不降级，legacy状态不洗白、不饿死正常candidate；
6. deletion proof：broker/SCM_RIGHTS/pidfd/sidecar creation/tombstone budget及对应测试真正删除；
7. suite：测试按Contract owner组织，marker正确，parked-Dolt unit通过；
8. container：最终HEAD镜像与Compose evidence对齐。

只有上述全部闭合后才能重新判断`S3 ready`。本计划本身和文档提交不代表实现已完成。

## 8. Step A inventory (working baseline `fb06619`)

文档设计基线仍是 `3616ef0`。Step A 冻结的工作树是其后的 `c6369a3`（ADR 0012 / 本计划）加
`fb06619`（notify 从第一页重启 cursor、startup 在 disk gate 前 reclaim、readiness 忘掉已
stamp 的 upload）。本节是执行记录，不升级为长期第二权威。

### 8.1 Production call graph and lock order

Eligibility 已统一：`artifact_retention.decide_artifact_bytes_deletion`，经
`ImportOperationStore.evaluate_artifact_bytes_deletion` / `can_delete_artifact_bytes`。

Ready-bytes 删除在 Step A 之前没有统一入口。三处复制 stamp/intent/receipt/residual 回调后
调用 `try_unlink_ready_artifact_with_recheck` → `try_unlink_owned_ready_artifact`：

- Worker：`ImportOperationExecutor._best_effort_delete_artifact_bytes`。SUCCEEDED 先持久化，
  再 best-effort 删 private ref / bytes。`ImportWorkerPool.set_lifecycle_notify` 唤醒 cleaner。
- Recovery / Admin：`cleanup_after_succeeded_correction`（private ref + staging + bytes）。
  Admin 是 stopped-service CLI，先拿 `DurableRootLock`。
- Cleaner：`ArtifactCleaner._process_candidate` 先 eligibility 与
  `classify_ready_artifact_path`；absent 记 `already_absent_unproven` 且不 stamp。

Step A 把上述 duplicated 回调抽到 `artifact_cleanup.cleanup_ready_artifact_bytes`，协议仍是
旧 owned unlink。Cleaner housekeeping（quarantine / receipt GC / residual reclaim / inventory）
不进入 facade。

非 ready-bytes、不要误收进 facade：

- upload 成功只 `notify` cleaner；
- mutation reconciliation 只清 import staging；
- admin `NOT_PUBLISHED` 只清 private ref + staging；
- `versioned_read/async_cleanup.py` 与 artifact bytes 无关。

锁序（HEAD，Step A 不改）：

1. 服务持有 durable-root lock；admin CLI 在服务停止时独占同一把锁。
2. Worker 另持 `repository_execution`。Cleanup 不持该锁。
3. Admission pin：ready inode `LOCK_EX`（阻塞）。
4. Owned unlink：tombstone reserve（ready dir flock）→ ready inode `LOCK_EX|LOCK_NB` →
   broker link/rename → control DB intent/stamp/residual → ftruncate/reclaim → unlock。
5. 目标「cleanup 取得 admission pin，同一临界区重读 eligibility」尚未实现。

`fb06619`：`notify()` 置 `_restart_cursor`，下次 sweep 从 page one 重扫；startup 在
`has_free_disk_admission` 之前调用 `reclaim_until_disk_admission`。

### 8.2 Stop-write / compatibility-read / deletable

`CONTROL_DB_USER_VERSION = 15`。不降 user_version。本步继续按 HEAD 写入；下表供 Step B/C。

| object | HEAD | later disposition | leftover blocks admission? |
| --- | --- | --- | --- |
| `bytes_deleted_at` | 仍写（成功 stamp） | **继续写** | 是：已 stamp 拒绝 import |
| intent 五列（at/dev/ino/phase/generation） | 仍写 | Step B **停写**，列留 ballast；CHECK 仍要求全空或完整 | **是**：active intent → `ImportArtifactBindingRejected` |
| receipt 三列 | 仍写（stamp 时从 intent 拷贝） | Step B **停写**，列留 ballast | 否（直接） |
| 表 `artifact_residual` | 仍写 | Step B **停写**；表 admin 必选，删表需 migration | 否（直接） |
| `cleanup_seq` INTEGER + unique/partial index + immutable trigger | 仍写 | **保留**（分页 / poison 隔离） | 否 |
| 索引 `(created_at, artifact_id) WHERE bytes_deleted_at IS NULL` | schema 仍在，生产 SELECT 已不用 | **ballast**；删索引需新 migration | 否 |
| sidecar `.deleting-` / `.detach-` / `.unlink-verify-` / `.unlink-stage-` 及 stage children | 仍创建 | Step B **停止创建**；磁盘 legal eligible 可 best-effort 收敛 | 间接：计入 tombstone budget，挡新 delete |
| `artifact_tombstone_budget`（默认 50_000，Compose `GATEWAY_REPOSITORY_ARTIFACT_TOMBSTONE_BUDGET`） | 仍接线 | Step B **删除**设置 / env / projected reservation | 间接（budget） |
| broker socket / SCM_RIGHTS / pidfd / helper / `_DirLocks` | 仍存在 | Step C **删除** | n/a |

磁盘最小 fixture（Step B 才造收敛器）：legal eligible ready、protected、malformed/ambiguous
sidecar、I/O failure。

### 8.3 Step B behavior deltas (not in Step A)

Step A Contract 冻结 HEAD：

- eligible `ENOENT` 幂等完成调用，**不**盖 `bytes_deleted_at`；ineligible missing 仍 fail closed。
- cleanup 与 admission 靠同一 ready inode flock 协作，不改协议。

Step B 才改：

- eligible `ENOENT` 可盖 `bytes_deleted_at`，readiness 视为完成；
- cleanup 先拿 admission pin，同一临界区重读 eligibility，再 dirfd unlink；
- 停止创建 sidecar / generation / receipt / residual / tombstone reservation。

## 9. Step B execution (from `60a19c4`)

工作基线是 Step A 提交 `60a19c4`，不是文档原先写的 `fb06619`。`fb06619` 之后没有
另一轮改 unlink/pin/sidecar 语义的优化修复。

已确认的范围裁决：

- Step B **不**要求 `test_artifact_cleanup.py` 全绿；该文件的 sidecar/intent/ENOENT
  旧断言留到 Step D 删除。mypy 对该模块 `ignore_errors`，避免为签名变化改写 1.1 万行。
- 新路径对 exact ready 名做同 UID `unlinkat(dir_fd=...)`，不经 broker。双 UID
  容器（artifacts `0750` broker-owned）直到 Step C 改所有权之前不可部署。不重建 Docker。
- Python 删除 `artifact_tombstone_budget` 设置与 facade 参数。Compose env
  `GATEWAY_REPOSITORY_ARTIFACT_TOMBSTONE_BUDGET` 留到 Step C。
- Cleanup 与 admission 争同一 ready inode flock：cleanup 侧 `LOCK_EX|LOCK_NB`（busy
  则重试），不复用 `ArtifactAdmissionPin` class（它关 dirfd、校验 size/SHA、缺文件无法 stamp）。
- `record_artifact_bytes_deleted` 不再要求 intent、不再填写 receipt；同一 UPDATE 清掉
  leftover intent 五列。PROTECTED leftover intent 不投影，admission 仍拒绝。

Production 入口：`cleanup_ready_artifact_bytes` → open owned ready → flock NB →
eligibility recheck → `unlinkat` → stamp。Eligible `ENOENT` 盖 `bytes_deleted_at`。
Cleaner housekeeping 仍可读/收敛 leftover sidecar，新成功路径不再创建。

## 10. Step C execution (from current HEAD after Step B)

本步删除 directory-broker 与双 UID 部署边界。生产 mkdir/publish/housekeeping 改本地
dirfd syscall；leftover `try_unlink_owned_*` 仍保留 `_broker_*` 函数名（实现已是本地
syscall）供 Step D 证明墙 monkeypatch。Compose `GATEWAY_REPOSITORY_ARTIFACT_TOMBSTONE_BUDGET`
已删除。容器不重建；静态 Dockerfile/entrypoint/Compose 测试改写为单一 `gateway` 主体。

因收集约束，`test_artifact_broker_r{19,20,21,22}.py` 与 conftest inprocess autouse 在本步
删除（计划原文把 broker 协议测试写在 Step D）。`test_artifact_cleanup.py` 仍留给 Step D。

## 11. Step D execution

删除 `tests/test_artifact_cleanup.py` 与对该文件的 mypy 豁免。conventions/§5 缺口迁到
`test_artifact_retention.py` / `test_artifact_cleaner.py` /
`test_artifact_cleanup_integration.py`（去 `rNN_` 名）。生产侧删除无调用者的
`try_unlink_owned_*` / `_broker_*` CREATE 路径；housekeeping restore 只 link 到 exact
UUID ready 名。不重建容器。
